from __future__ import annotations

import hmac
import json
import os
import re
import time
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from core.settings import PRIVACY_NER_BACKEND, PRIVACY_SALT_FILE, PRIVACY_SALT_HEX
from utils.timeutil import utc_now_iso

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?x)(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\w)")
_URL_RE = re.compile(r"(?i)\bhttps?://[^\s]+")
_ID_RE = re.compile(r"(?i)\b(?:\d{15}|\d{17}[\dX])\b")
_ADDR_RE = re.compile(
    r"(?:[\u4e00-\u9fff]{2,20}(?:省|市|区|县))?[\u4e00-\u9fff0-9A-Za-z\-]{1,20}(?:路|街|道)\d{1,4}号?"
)

_ORG_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:公司|集团|大学|学院|银行|医院|学校)")
_LOC_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{1,30}(?:省|市|区|县|镇|路|街|国|城)")
_SENT_SPLIT_RE = re.compile(r"(?<=[\.!?。！？])\s+")

_ENTITY_PREFIX: Dict[str, str] = {
    "PERSON": "P",
    "ORG": "O",
    "LOC": "L",
}


def _ensure_salt() -> bytes:
    salt_hex = (os.getenv("PRIVACY_SALT_HEX") or PRIVACY_SALT_HEX or "").strip()
    salt_file = (os.getenv("PRIVACY_SALT_FILE") or PRIVACY_SALT_FILE or "").strip()

    if salt_hex:
        try:
            return bytes.fromhex(salt_hex)
        except Exception as e:
            raise ValueError(f"invalid PRIVACY_SALT_HEX: {e}")

    p = Path(salt_file).expanduser()
    if p.exists():
        return p.read_bytes()

    p.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(32)
    p.write_bytes(salt)
    return salt


def _stable_pseudo(*, salt: bytes, entity_type: str, value: str) -> str:
    prefix = _ENTITY_PREFIX.get(entity_type)
    if not prefix:
        raise ValueError(f"unsupported entity_type: {entity_type}")
    normalized = value.strip().lower().encode("utf-8")
    digest = hmac.new(salt, normalized, sha256).hexdigest()[:4]
    return f"{prefix}#{digest}"


def _replace_pii(text: str) -> str:
    out = text
    out = _EMAIL_RE.sub("[EMAIL]", out)
    out = _PHONE_RE.sub("[PHONE]", out)
    out = _URL_RE.sub("[URL]", out)
    out = _ID_RE.sub("[ID]", out)
    out = _ADDR_RE.sub("[ADDR]", out)
    return out


def _collect_candidates_simple(text: str) -> List[Tuple[str, str]]:
    cands: List[Tuple[str, str]] = []
    for m in _ORG_RE.finditer(text):
        cands.append(("ORG", m.group(0)))
    for m in _LOC_RE.finditer(text):
        cands.append(("LOC", m.group(0)))
    # Keep PERSON heuristic conservative: only after "和/与/跟" markers.
    for m in re.finditer(r"(?:和|与|跟)([\u4e00-\u9fff]{2,3})", text):
        cands.append(("PERSON", m.group(1)))
    return cands


def _collect_candidates_lexicon(text: str, entity_hints: Dict[str, Iterable[str]]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for et in ("PERSON", "ORG", "LOC"):
        for item in entity_hints.get(et, []) or []:
            s = str(item or "").strip()
            if s and s in text:
                out.append((et, s))
    return out


def _collect_entities(text: str, *, ner_backend: str, entity_hints: Dict[str, Iterable[str]] | None) -> List[Tuple[str, str]]:
    b = (ner_backend or "none").strip().lower()
    if b == "none":
        return []
    if b == "lexicon":
        return _collect_candidates_lexicon(text, entity_hints or {})
    if b == "simple":
        return _collect_candidates_simple(text)
    return []


def _apply_pseudonyms(text: str, entities: List[Tuple[str, str]], salt: bytes) -> Tuple[str, List[Dict[str, str]]]:
    red = text
    used: List[Dict[str, str]] = []
    seen = set()
    # Longest-first reduces partial-overwrite issues.
    for et, val in sorted(entities, key=lambda x: len(x[1]), reverse=True):
        raw = str(val or "").strip()
        if not raw:
            continue
        pseudo = _stable_pseudo(salt=salt, entity_type=et, value=raw)
        red = red.replace(raw, pseudo)
        key = (et, pseudo)
        if key in seen:
            continue
        seen.add(key)
        used.append({"type": et, "pseudo_id": pseudo})
    return red, used


def _extract_facts(redacted_text: str, *, min_n: int = 3, max_n: int = 8) -> List[str]:
    sents = [s.strip() for s in _SENT_SPLIT_RE.split(redacted_text) if s.strip()]
    if not sents:
        return ["No content provided.", "No content provided.", "No content provided."][:min_n]
    facts = sents[:max_n]
    while len(facts) < min_n:
        facts.append(facts[-1])
    return facts


def _extract_tags(redacted_text: str) -> List[str]:
    low = redacted_text.lower()
    rules = [
        ("work", r"\b(work|meeting|deadline)\b|工作|上班|项目"),
        ("health", r"\b(sleep|insomnia|sick)\b|睡|失眠|身体|生病"),
        ("study", r"\b(study|english|learn)\b|学习|英语|复习"),
        ("social", r"\b(friend|party|date)\b|朋友|聚会|社交"),
    ]
    out: List[str] = []
    for tag, pat in rules:
        if re.search(pat, low):
            out.append(tag)
    return out[:8]


def build_cloud_contract_v1(
    *,
    raw_text: str,
    source: str = "local_privacy_gate",
    ner_backend: str | None = None,
    entity_hints: Dict[str, Iterable[str]] | None = None,
) -> Dict[str, Any]:
    """Build a privacy-preserving cloud contract from local raw text.

    - Uses HMAC-SHA256(salt, value) for stable pseudonyms.
    - contract_id uses UUID format.
    - DATE entities are intentionally not exported; use coarse time_bucket instead.
    """

    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("raw_text is empty")

    salt = _ensure_salt()
    redacted = _replace_pii(text)
    backend = (
        (ner_backend or "").strip().lower()
        or (os.getenv("PRIVACY_NER_BACKEND") or PRIVACY_NER_BACKEND or "none").strip().lower()
    )
    entities = _collect_entities(redacted, ner_backend=backend, entity_hints=entity_hints)
    redacted, entity_rows = _apply_pseudonyms(redacted, entities, salt)

    facts = _extract_facts(redacted, min_n=3, max_n=8)
    timeline = [{"event_ts": int(time.time()), "summary": facts[0]}]
    # Use "today" bucket to avoid exposing exact dates from text.
    time_bucket = utc_now_iso()[:10]

    return {
        "contract_version": "v1",
        "contract_id": str(uuid.uuid4()),
        "source": source,
        "created_at": utc_now_iso(),
        "time_bucket": time_bucket,
        "text_redacted": redacted,
        "facts": facts,
        "timeline": timeline,
        "entities": entity_rows,
        "tags": _extract_tags(redacted),
    }


def build_cloud_contract_json(**kwargs: Any) -> str:
    return json.dumps(build_cloud_contract_v1(**kwargs), ensure_ascii=False, sort_keys=True)
