# block_analyze.py
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from llm.ollama_client import OllamaClient
from pipeline.analysis_quality import attach_analysis_quality

from core.settings import (
    MAX_BLOCK_CHARS,
    MIN_BLOCK_CHARS,
    PHI_MODEL,
    PHI_NUM_PREDICT,
    PROMPT_VERSION_BLOCK,
)

# Back-compat exports used by scripts (do not rename).
PROMPT_VERSION = f"{PROMPT_VERSION_BLOCK}:staged_v1"


# Keep generation short to reduce idle-time analysis latency.
# You can override per machine / model.
STAGE_GENERATE_ATTEMPTS = max(1, int(os.getenv("ANALYSIS_STAGE_ATTEMPTS", "2")))



class BlockInputError(ValueError):
    pass


class AnalysisValidationError(RuntimeError):
    pass


def _count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", str(text or "")))


def _extract_latin_words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text or ""))


def _raw_requires_chinese(raw_text: str) -> bool:
    raw = str(raw_text or "")
    return _count_cjk(raw) >= max(24, len(_extract_latin_words(raw)) * 2)


def _collect_output_text(obj: Dict[str, Any]) -> str:
    fields: List[str] = [str(obj.get("summary_1_3") or ""), str(obj.get("open_insight") or "")]
    for key in (
        "facts",
        "todos",
        "topics",
        "evidence_spans",
        "psychological_themes",
        "tensions",
        "needs",
        "patterns",
        "memory_candidates",
    ):
        value = obj.get(key) or []
        if isinstance(value, list):
            fields.extend(str(x or "") for x in value)
    return " ".join(fields)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _split_sentences(text: str) -> List[str]:
    raw = str(text or "").replace("\r\n", "\n")
    pieces = re.split(r"(?<=[。！？!?])|[\n]+", raw)
    out: List[str] = []
    for piece in pieces:
        s = str(piece or "").strip()
        if not s:
            continue
        out.append(s)
    return out


def _split_clauses(text: str) -> List[str]:
    raw = str(text or "")
    parts = re.split(r"[，,；;、]", raw)
    out: List[str] = []
    for part in parts:
        s = str(part or "").strip()
        if not s:
            continue
        out.append(s)
    return out


def _short_clause(text: str, *, max_chars: int = 30) -> str:
    s = str(text or "").strip()
    if len(s) <= max_chars:
        return s
    clauses = _split_clauses(s)
    for clause in clauses:
        if 6 <= len(clause) <= max_chars:
            return clause
    return s[:max_chars].rstrip("，,；;、 ")


def _build_evidence_candidates(raw_text: str, *, limit: int = 10) -> List[Dict[str, str]]:
    seen = set()
    candidates: List[Dict[str, str]] = []
    for sent in _split_sentences(raw_text):
        for clause in _split_clauses(sent):
            snippet = _short_clause(clause, max_chars=30)
            if len(snippet) < 6:
                continue
            key = _normalize_text(snippet)
            if not key or key in seen:
                continue
            if len(key) > 40:
                key = key[:40]
            seen.add(key)
            candidates.append(
                {
                    "id": f"e{len(candidates) + 1}",
                    "text": snippet,
                }
            )
            if len(candidates) >= limit:
                return candidates
    return candidates


def _has_unwanted_english(*, obj: Dict[str, Any], raw_text: str) -> bool:
    if not _raw_requires_chinese(raw_text):
        return False

    output = _collect_output_text(obj)
    allowed = {w.lower() for w in _extract_latin_words(raw_text)}
    latin_words = [w.lower() for w in _extract_latin_words(output)]
    suspicious = [w for w in latin_words if w not in allowed]
    cjk_out = _count_cjk(output)

    if len(suspicious) >= 20 and cjk_out > 20:
        return True
    if len(suspicious) >= 8 and cjk_out > 40:
        return True
    if latin_words and (len(suspicious) / max(len(latin_words), 1)) >= 0.5 and cjk_out > 20:
        return True
    return False


def _dedupe(items: List[str], *, limit: int = 6) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _looks_like_noise_block(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return True
    if re.fullmatch(r"[xX]{40,}", s):
        return True

    lowered = s.lower()
    short_noise_markers = (
        "smoke_frontend_api",
        "debug save fields",
        "write to storage db check",
        "append-test",
        "sqlite entry",
        "smoke:",
        "selfcheck:",
    )
    if len(s) <= 180 and any(marker in lowered for marker in short_noise_markers):
        return True
    marker_hits = sum(lowered.count(marker) for marker in short_noise_markers)
    timestamp_lines = len(re.findall(r"---\s*\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}", lowered))
    if marker_hits >= 2:
        return True
    if marker_hits >= 1 and timestamp_lines >= 2:
        return True

    lines = [line.strip() for line in s.splitlines() if line.strip()]
    if not lines:
        return True
    noisy_lines = 0
    for line in lines:
        low = line.lower()
        if any(marker in low for marker in short_noise_markers):
            noisy_lines += 1
            continue
        if re.fullmatch(r"[-:\dTZ\s]{8,}", line):
            noisy_lines += 1
            continue
    if len(lines) >= 3 and noisy_lines / max(1, len(lines)) >= 0.6:
        return True
    return False


def _extract_json_object(s: str) -> str:
    if not s:
        return s
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return s.strip()
    return s[start : end + 1].strip()


def _repair_json_common_issues(s: str) -> str:
    s = _extract_json_object(str(s or "").replace("\r\n", "\n"))
    if not s:
        return s

    # Some providers emit literal newlines inside JSON strings, which breaks
    # json.loads even though the semantic content is otherwise recoverable.
    out: List[str] = []
    in_string = False
    escape = False
    for ch in s:
        if in_string:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                continue
            if ch == "\t":
                out.append(" ")
                continue
            out.append(ch)
            continue
        out.append(ch)
        if ch == '"':
            in_string = True

    repaired = "".join(out).strip()
    # Tolerate trailing commas before object/array closures.
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _repair_json_missing_commas(s: str) -> str:
    text = str(s or "")
    if not text:
        return text

    out: List[str] = []
    in_string = False
    escape = False
    prev_sig = ""

    def _starts_value(ch: str) -> bool:
        return ch == '"' or ch == "{" or ch == "[" or ch in "-0123456789tfn"

    def _ends_value(ch: str) -> bool:
        return ch == '"' or ch == "}" or ch == "]" or ch in "0123456789eln"

    for ch in text:
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
                prev_sig = '"'
            continue

        if ch == '"':
            if prev_sig and _ends_value(prev_sig):
                out.append(",")
                prev_sig = ","
            out.append(ch)
            in_string = True
            continue

        if ch.isspace():
            out.append(ch)
            continue

        if _starts_value(ch) and prev_sig and _ends_value(prev_sig):
            out.append(",")
            prev_sig = ","

        out.append(ch)
        prev_sig = ch

    return "".join(out)


def _try_repair_json_lines(s: str) -> str:
    s = s.replace("\r\n", "\n")
    cleaned: List[str] = []
    for line in s.split("\n"):
        ls = line.lstrip()
        if not ls:
            continue
        if ls.startswith("{") or ls.startswith("}"):
            cleaned.append(line)
            continue
        if ls.startswith('"') and '":' in ls:
            cleaned.append(line)
            continue
    return "\n".join(cleaned).strip()


def _coerce_signal(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 10 else None
    if isinstance(v, float):
        if v != v:
            return None
        return int(round(v)) if 0.0 <= v <= 10.0 else None
    if isinstance(v, str):
        m = re.search(r"(-?\d+(?:\.\d+)?)", v)
        if not m:
            return None
        try:
            num = float(m.group(1))
        except Exception:
            return None
        return int(round(num)) if 0.0 <= num <= 10.0 else None
    return None


def _normalize(obj: Dict[str, Any]) -> Dict[str, Any]:
    obj.setdefault("evidence_spans", [])
    obj.setdefault("reflection_depth", None)
    obj.setdefault("open_insight", "")
    obj.setdefault("psychological_themes", [])
    obj.setdefault("tensions", [])
    obj.setdefault("needs", [])
    obj.setdefault("patterns", [])
    obj.setdefault("memory_candidates", [])

    sig = obj.get("signals")
    if isinstance(sig, dict):
        for k in ("mood", "stress", "sleep", "exercise", "social", "work"):
            sig[k] = _coerce_signal(sig.get(k))

    for k in ("facts", "todos", "topics", "evidence_spans", "psychological_themes", "tensions", "needs", "patterns", "memory_candidates"):
        v = obj.get(k)
        if v is None:
            obj[k] = []
        elif isinstance(v, list):
            obj[k] = [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
        else:
            obj[k] = []

    if "summary_1_3" in obj and obj["summary_1_3"] is not None and not isinstance(obj["summary_1_3"], str):
        obj["summary_1_3"] = str(obj["summary_1_3"])
    if "open_insight" in obj and obj["open_insight"] is not None and not isinstance(obj["open_insight"], str):
        obj["open_insight"] = str(obj["open_insight"])

    rd = obj.get("reflection_depth")
    if rd is None:
        obj["reflection_depth"] = None
    elif isinstance(rd, (int, float)):
        rdi = int(round(float(rd)))
        obj["reflection_depth"] = rdi if 0 <= rdi <= 3 else None
    else:
        obj["reflection_depth"] = None

    return obj


def _validate(obj: Dict[str, Any]) -> None:
    required = ["summary_1_3", "signals", "facts", "todos", "topics", "open_insight"]
    missing = [k for k in required if k not in obj]
    if missing:
        raise AnalysisValidationError(f"missing keys: {missing}")

    if not isinstance(obj["summary_1_3"], str) or not obj["summary_1_3"].strip():
        raise AnalysisValidationError("summary_1_3 must be a non-empty string")
    if not isinstance(obj["open_insight"], str) or not obj["open_insight"].strip():
        raise AnalysisValidationError("open_insight must be a non-empty string")

    signals = obj["signals"]
    if not isinstance(signals, dict):
        raise AnalysisValidationError("signals must be an object")

    for k in ("mood", "stress", "sleep", "exercise", "social", "work"):
        if k not in signals:
            raise AnalysisValidationError(f"missing signals.{k}")
        v = signals.get(k)
        if v is None:
            continue
        if not isinstance(v, int) or v < 0 or v > 10:
            raise AnalysisValidationError(f"signals.{k} must be int 0-10 or null")

    for k in ("facts", "todos", "topics", "evidence_spans", "psychological_themes", "tensions", "needs", "patterns", "memory_candidates"):
        if not isinstance(obj.get(k), list) or any(not isinstance(x, str) for x in obj.get(k, [])):
            raise AnalysisValidationError(f"{k} must be an array of strings")

    rd = obj.get("reflection_depth")
    if rd is not None and (not isinstance(rd, int) or rd < 0 or rd > 3):
        raise AnalysisValidationError("reflection_depth must be int 0-3 or null")


def _normalize_evidence_obj(obj: Dict[str, Any], *, raw_text: str, candidates: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    units_in = obj.get("evidence_units")
    normalized_units: List[Dict[str, str]] = []
    raw_compact = _normalize_text(raw_text)
    candidate_map = {str(item.get("id") or ""): str(item.get("text") or "") for item in (candidates or []) if str(item.get("id") or "").strip()}

    evidence_ids = obj.get("evidence_ids")
    if isinstance(evidence_ids, list) and candidate_map:
        for evidence_id in evidence_ids:
            eid_raw = str(evidence_id or "").strip()
            if not eid_raw:
                continue
            eid = eid_raw if eid_raw.startswith("e") else f"e{eid_raw}"
            quote = candidate_map.get(eid, "").strip()
            if not quote:
                continue
            if _normalize_text(quote) not in raw_compact:
                continue
            normalized_units.append({"id": eid, "quote": quote, "kind": "evidence", "topic": ""})
            if len(normalized_units) >= 4:
                break

    if isinstance(units_in, list):
        for item in units_in:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            evidence_id = str(item.get("id") or "").strip()
            kind = str(item.get("kind") or "").strip() or "evidence"
            topic = str(item.get("topic") or "").strip()
            if not quote:
                continue
            if _normalize_text(quote) not in raw_compact:
                continue
            normalized_units.append({"id": evidence_id or f"e{len(normalized_units) + 1}", "quote": quote, "kind": kind, "topic": topic})
            if len(normalized_units) >= 6:
                break

    topics = obj.get("topic_candidates")
    if isinstance(topics, list):
        topic_candidates = _dedupe([str(x or "") for x in topics], limit=4)
    else:
        topic_candidates = []

    entry_shape = str(obj.get("entry_shape") or "").strip().lower()
    if entry_shape not in {"single_thread", "multi_thread", "mixed"}:
        entry_shape = "mixed"

    return {
        "evidence_units": normalized_units,
        "topic_candidates": topic_candidates,
        "entry_shape": entry_shape,
        "candidate_count": len(candidates or []),
    }


def _evidence_refs(evidence_obj: Dict[str, Any]) -> List[Dict[str, str]]:
    refs: List[Dict[str, str]] = []
    for item in evidence_obj.get("evidence_units") or []:
        if not isinstance(item, dict):
            continue
        refs.append(
            {
                "id": str(item.get("id") or "").strip(),
                "quote": str(item.get("quote") or "").strip(),
                "kind": str(item.get("kind") or "").strip(),
                "topic": str(item.get("topic") or "").strip(),
            }
        )
    return refs


def _validate_evidence_obj(obj: Dict[str, Any], *, raw_text: str) -> None:
    units = obj.get("evidence_units")
    if not isinstance(units, list):
        raise AnalysisValidationError("evidence_units must be an array")
    if len(units) <= 0:
        raise AnalysisValidationError("evidence_units must contain at least one selected evidence item")
    raw_compact = _normalize_text(raw_text)
    for item in units:
        if not isinstance(item, dict):
            raise AnalysisValidationError("evidence_units must contain objects")
        quote = str(item.get("quote") or "").strip()
        if not quote:
            raise AnalysisValidationError("evidence_units.quote must be non-empty")
        if _normalize_text(quote) not in raw_compact:
            raise AnalysisValidationError("evidence_units.quote must be an exact quote from raw_text")


def _parse_evidence_or_raise(raw: str, *, raw_text: str) -> Dict[str, Any]:
    candidates = _build_evidence_candidates(raw_text)
    cand = _extract_json_object(raw)
    try:
        obj = json.loads(cand)
    except Exception:
        repaired = _repair_json_common_issues(cand)
        try:
            obj = json.loads(repaired)
        except Exception as e:
            repaired_lines = _try_repair_json_lines(repaired)
            try:
                obj = json.loads(repaired_lines)
            except Exception as e2:
                raise AnalysisValidationError(f"non-JSON evidence output: {e2}") from e2
    if not isinstance(obj, dict):
        raise AnalysisValidationError("evidence top-level must be an object")
    obj = _normalize_evidence_obj(obj, raw_text=raw_text, candidates=candidates)
    _validate_evidence_obj(obj, raw_text=raw_text)
    return obj


def _normalize_deep_obj(obj: Dict[str, Any]) -> Dict[str, Any]:
    main_threads = obj.get("main_threads")
    if isinstance(main_threads, list):
        main_threads_norm = _dedupe([str(x or "") for x in main_threads], limit=3)
    else:
        main_threads_norm = []
    return {
        "main_threads": main_threads_norm,
        "core_conflict": str(obj.get("core_conflict") or "").strip(),
        "core_need": str(obj.get("core_need") or "").strip(),
        "behavior_pattern": str(obj.get("behavior_pattern") or "").strip(),
        "deep_analysis": str(obj.get("deep_analysis") or "").strip(),
        "confidence_notes": str(obj.get("confidence_notes") or "").strip(),
    }


def _validate_deep_obj(obj: Dict[str, Any]) -> None:
    if not isinstance(obj.get("main_threads"), list):
        raise AnalysisValidationError("deep.main_threads must be an array")
    if not str(obj.get("deep_analysis") or "").strip():
        raise AnalysisValidationError("deep.deep_analysis must be non-empty")
    if not any(str(obj.get(k) or "").strip() for k in ("core_conflict", "core_need", "behavior_pattern")):
        raise AnalysisValidationError("deep stage must include at least one concrete conflict/need/pattern")


def _parse_deep_or_raise(raw: str, *, raw_text: str) -> Dict[str, Any]:
    cand = _extract_json_object(raw)
    try:
        obj = json.loads(cand)
    except Exception:
        repaired = _repair_json_common_issues(cand)
        try:
            obj = json.loads(repaired)
        except Exception as e:
            repaired_lines = _try_repair_json_lines(repaired)
            try:
                obj = json.loads(repaired_lines)
            except Exception as e2:
                raise AnalysisValidationError(f"non-JSON deep output: {e2}") from e2
    if not isinstance(obj, dict):
        raise AnalysisValidationError("deep top-level must be an object")
    obj = _normalize_deep_obj(obj)
    _validate_deep_obj(obj)
    if _raw_requires_chinese(raw_text):
        deep_text = " ".join(
            [*(obj.get("main_threads") or []), obj.get("core_conflict") or "", obj.get("core_need") or "", obj.get("behavior_pattern") or "", obj.get("deep_analysis") or ""]
        )
        if _has_unwanted_english(
            obj={
                "summary_1_3": "",
                "open_insight": deep_text,
                "facts": [],
                "todos": [],
                "topics": [],
                "evidence_spans": [],
                "psychological_themes": [],
                "tensions": [],
                "needs": [],
                "patterns": [],
                "memory_candidates": [],
            },
            raw_text=raw_text,
        ):
            raise AnalysisValidationError("deep output contains unsupported English text for Chinese diary")
    return obj


def _build_evidence_messages(*, title: str | None, raw_text: str) -> List[Dict[str, str]]:
    template = {
        "evidence_ids": [],
        "topic_candidates": [],
        "entry_shape": "mixed",
    }
    candidates = _build_evidence_candidates(raw_text)
    sys = (
        "You extract direct evidence from a diary block. "
        "Return ONE valid JSON object only. No markdown. No commentary. "
        "Do not analyze personality yet. "
        "If the diary block is mainly Chinese, all non-candidate text must be in Chinese. "
        "Select evidence by candidate id only."
    )
    header = f"TITLE: {(title or '').strip()}\n" if (title or "").strip() else ""
    user = (
        "Build evidence selection from the DIARY BLOCK.\n"
        f"TEMPLATE: {json.dumps(template, ensure_ascii=False)}\n\n"
        "Rules:\n"
        "- evidence_ids: choose 1-4 ids from the candidate list only.\n"
        "- Never rewrite candidate text. Never output long quotes manually.\n"
        "- For mixed or multi-thread blocks, choose only the 2-3 most informative threads, not every subplot.\n"
        "- topic_candidates: 1-3 concrete topics.\n"
        "- entry_shape: single_thread, multi_thread, or mixed.\n"
        "- Do not summarize the whole diary.\n"
        "- Do not translate the diary.\n\n"
        f"CANDIDATES:\n{json.dumps(candidates, ensure_ascii=False)}\n\n"
        "DIARY BLOCK:\n"
        f"{header}{raw_text.strip()}\n"
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _build_deep_messages(*, title: str | None, raw_text: str, evidence_obj: Dict[str, Any]) -> List[Dict[str, str]]:
    template = {
        "main_threads": [],
        "core_conflict": "",
        "core_need": "",
        "behavior_pattern": "",
        "deep_analysis": "",
        "confidence_notes": "",
    }
    entry_shape = str(evidence_obj.get("entry_shape") or "").strip().lower()
    topic_candidates = evidence_obj.get("topic_candidates") or []
    mode = "multi_track" if entry_shape in {"multi_thread", "mixed"} or (isinstance(topic_candidates, list) and len(topic_candidates) >= 3) else "single_track"
    mode_guidance = (
        "Mode: single_track.\n"
        "- Prefer one clear main thread.\n"
        "- Keep the conflict, need, and pattern centered on the same arc.\n"
        "- Do not invent side themes unless evidence clearly supports them.\n\n"
        if mode == "single_track"
        else
        "Mode: multi_track.\n"
        "- First separate the block into 2-3 threads by importance.\n"
        "- Then identify which one carries the main emotional or practical center of gravity.\n"
        "- Keep the analysis selective; do not summarize every subplot.\n"
        "- If the threads are loosely connected, say so in confidence_notes instead of forcing one fake grand theory.\n\n"
    )
    sys = (
        "You do deep diary analysis grounded in evidence. "
        "Return ONE valid JSON object only. No markdown. No commentary. "
        "Use the evidence units as anchors. "
        "If the diary block is mainly Chinese, all analysis text must be in Chinese."
    )
    header = f"TITLE: {(title or '').strip()}\n" if (title or "").strip() else ""
    user = (
        "Use the evidence units to produce a deep but grounded reading.\n"
        f"TEMPLATE: {json.dumps(template, ensure_ascii=False)}\n\n"
        "Rules:\n"
        "- main_threads: 1-2 major threads only, concrete and short.\n"
        "- core_conflict: one concise sentence naming the main inner or situational conflict.\n"
        "- core_need: one concise sentence naming the unmet need or stabilizer.\n"
        "- behavior_pattern: one short concrete pattern if visible; otherwise keep it brief and cautious.\n"
        "- deep_analysis: 1-2 sentences only, grounded, specific, no generic diary clichés.\n"
        "- confidence_notes: one short sentence if uncertainty matters; otherwise keep it minimal.\n"
        "- Keep every field compact. Prefer shorter wording over completeness.\n"
        "- Stay grounded in the selected evidence refs below.\n"
        "- Do not translate the diary.\n"
        "- Do not output final database fields like signals/facts/todos.\n\n"
        f"{mode_guidance}"
        f"EVIDENCE REFS:\n{json.dumps(_evidence_refs(evidence_obj), ensure_ascii=False)}\n\n"
        "DIARY BLOCK:\n"
        f"{header}{raw_text.strip()}\n"
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _build_normalize_messages(*, title: str | None, raw_text: str, evidence_obj: Dict[str, Any], deep_obj: Dict[str, Any]) -> List[Dict[str, str]]:
    template = {
        "summary_1_3": "",
        "open_insight": "",
        "signals": {"mood": None, "stress": None, "sleep": None, "exercise": None, "social": None, "work": None},
        "facts": [],
        "todos": [],
        "topics": [],
        "evidence_spans": [],
        "psychological_themes": [],
        "tensions": [],
        "needs": [],
        "patterns": [],
        "memory_candidates": [],
        "reflection_depth": None,
    }
    entry_shape = str(evidence_obj.get("entry_shape") or "").strip().lower()
    topic_candidates = evidence_obj.get("topic_candidates") or []
    mode = "multi_track" if entry_shape in {"multi_thread", "mixed"} or (isinstance(topic_candidates, list) and len(topic_candidates) >= 3) else "single_track"
    mode_guidance = (
        "\nMode: single_track.\n"
        "- summary_1_3 should center on one dominant event or concern.\n"
        "- open_insight should stay close to that same line and avoid branching out.\n"
        "- topics should usually be 1-2 items.\n"
        "- tensions / needs / patterns should only be filled when clearly supported.\n\n"
        if mode == "single_track"
        else
        "\nMode: multi_track.\n"
        "- summary_1_3 should name the 1-2 most important threads, not every thread.\n"
        "- open_insight should explain the dominant conflict behind the main thread, while acknowledging multi-threaded structure when needed.\n"
        "- topics may contain 2-3 items, ordered by importance.\n"
        "- evidence_spans should come from the dominant threads only.\n"
        "- Do not flatten everything into one fake theme, and do not list every event mechanically.\n\n"
    )

    sys = (
        "You are a strict JSON normalization engine. "
        "Return ONE single JSON object ONLY. No markdown, no code fences, no commentary. "
        "Output must be valid JSON and must keep keys exactly as in TEMPLATE. "
        "Return compact single-line JSON only. Every member and array item must be separated by a comma. "
        "No extra keys. facts/todos/topics/evidence_spans/psychological_themes/tensions/needs/patterns/memory_candidates are arrays of strings. "
        "signal scores are int 0-10 or null. reflection_depth is int 0-3 or null. "
        "summary_1_3 is a compact factual overview grounded in the evidence. "
        "open_insight is a fuller interpretation grounded in the evidence and deep analysis. "
        "Do NOT rewrite or paraphrase the diary block line by line. "
        "Do NOT copy long spans from the diary into summary_1_3 or open_insight. "
        "Avoid generic phrases such as '记录当天在做的事' or '不是单纯记流水'. "
        "If evidence is limited or the block is multi-threaded, stay conservative and say less rather than inventing patterns. "
        "If the diary block is mainly Chinese, then summary_1_3, open_insight, facts, todos, topics, psychological_themes, tensions, needs, patterns, and memory_candidates MUST all be written in Chinese. "
        "Do NOT translate the diary into English. Do NOT mix in English sentences. "
        "Only keep English words that already appear in the diary block as product names, acronyms, or quoted evidence."
    )

    header = f"TITLE: {(title or '').strip()}\n" if (title or "").strip() else ""
    user = (
        "Normalize the evidence and deep analysis into the final schema.\n"
        f"TEMPLATE: {json.dumps(template, ensure_ascii=False)}\n\n"
        "Guidance:\n"
        "- summary_1_3: 1-2 sentences, grounded, concise, mention the actual concern or event.\n"
        "- open_insight: 1-2 sentences only, grounded, specific, derived from evidence + deep analysis.\n"
        "- summary_1_3 and open_insight must be analytical, not a rewritten diary.\n"
        "- Never copy the diary block wholesale into summary_1_3 or open_insight.\n"
        "- summary_1_3 must mention the concrete event or concern in this entry, not a generic diary description.\n"
        "- open_insight must mention the concrete conflict, need, or pattern from this entry, but stay conservative when evidence is weak.\n"
        "- If the diary block is mainly Chinese, all output text must stay in Chinese except product names/acronyms already present in the diary block.\n"
        "- Never provide English translations of the diary.\n"
        "- facts: 0-3 items only.\n"
        "- topics: 1-3 specific topics, ordered by importance.\n"
        "- psychological_themes: 0-2 items.\n"
        "- tensions: 0-2 conflicts, ambivalence, avoidance, or push-pull dynamics.\n"
        "- needs: 0-2 unmet needs, wishes, or stabilizers implied by the text.\n"
        "- patterns: 0-2 behavioral or emotional patterns visible in this block.\n"
        "- memory_candidates: 0-2 details worth remembering long-term.\n"
        "- evidence_spans: choose 1-3 short verbatim phrases from evidence_units only.\n"
        "- Keep arrays short and selective. Do not try to preserve every subplot.\n"
        "- BAD generic examples: '这篇主要在记录当天在做的事', '这篇不是单纯记流水'.\n"
        "- GOOD direction: point to the exact concern, exact conflict, exact trigger, and exact evidence.\n"
        f"{mode_guidance}"
        f"EVIDENCE REFS:\n{json.dumps(_evidence_refs(evidence_obj), ensure_ascii=False)}\n\n"
        f"DEEP ANALYSIS JSON:\n{json.dumps(deep_obj, ensure_ascii=False)}\n\n"
        "DIARY BLOCK:\n"
        f"{header}{raw_text.strip()}\n"
    )

    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _build_fix_messages(*, raw_text: str, bad_output: str, template_obj: Dict[str, Any], stage_name: str, parse_error: str | None = None) -> List[Dict[str, str]]:
    sys = (
        "You are a JSON repair engine. Rewrite into ONE valid JSON object ONLY. "
        "No markdown, no commentary, no extra keys. Keep the required keys and types. "
        "Return compact single-line JSON only. Every member and array item must be separated by a comma. "
        "If the source diary was mainly Chinese, all non-evidence text fields must stay in Chinese and you must not output English translations. "
        "Preserve the intended stage and fill the template faithfully."
    )
    user = (
        f"STAGE: {stage_name}\n"
        f"TEMPLATE: {json.dumps(template_obj, ensure_ascii=False)}\n\n"
        + (f"PARSE ERROR:\n{parse_error}\n\n" if parse_error else "")
        + "SOURCE DIARY BLOCK:\n" + (raw_text or "")
        + "\n\nBAD OUTPUT:\n" + (bad_output or "")
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _parse_or_raise(raw: str) -> Dict[str, Any]:
    cand = _extract_json_object(raw)
    try:
        obj = json.loads(cand)
    except Exception:
        repaired = _repair_json_common_issues(cand)
        try:
            obj = json.loads(repaired)
        except Exception as e:
            repaired_commas = _repair_json_missing_commas(repaired)
            try:
                obj = json.loads(repaired_commas)
            except Exception:
                repaired_lines = _try_repair_json_lines(repaired_commas)
                try:
                    obj = json.loads(repaired_lines)
                except Exception as e2:
                    raise AnalysisValidationError(f"non-JSON output: {e2}") from e2

    if not isinstance(obj, dict):
        raise AnalysisValidationError("top-level must be an object")

    obj = _normalize(obj)
    _validate(obj)
    return obj


@dataclass
class BlockAnalyzeResult:
    analysis: Dict[str, Any]
    ms: int
    raw_output: str


@dataclass
class StageCallResult:
    output: str
    ms: int
    model: str


StageCaller = Callable[[str, List[Dict[str, str]], Optional[Dict[str, Any]], int], Awaitable[StageCallResult]]
StageRecorder = Callable[..., None]


def _stage_prompt_version(stage: str) -> str:
    return f"{PROMPT_VERSION}:{stage}"


def _safe_stage_meta(*, title: str | None, raw_text: str, evidence_obj: Optional[Dict[str, Any]] = None, deep_obj: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    meta: Dict[str, Any] = {
        "title": (title or "").strip() or None,
        "raw_chars": len(raw_text or ""),
    }
    if evidence_obj is not None:
        meta["evidence_count"] = len(evidence_obj.get("evidence_units") or [])
        meta["topics"] = evidence_obj.get("topic_candidates") or []
        meta["entry_shape"] = str(evidence_obj.get("entry_shape") or "")
    if deep_obj is not None:
        meta["deep_main_threads"] = deep_obj.get("main_threads") or []
    return meta


def _stage_backend_from_model(model: Optional[str]) -> Optional[str]:
    text = str(model or "").strip().lower()
    if text.startswith("local:"):
        return "local"
    if text.startswith("cloud:"):
        return "cloud"
    return None


def _record_stage_safe(stage_recorder: Optional[StageRecorder], **kwargs: Any) -> None:
    if not stage_recorder:
        return
    try:
        stage_recorder(**kwargs)
    except TypeError:
        kwargs.pop("backend_override", None)
        stage_recorder(**kwargs)


async def _run_json_stage(
    *,
    stage_name: str,
    title: str | None,
    raw_text: str,
    template_obj: Dict[str, Any],
    build_messages: Callable[[], List[Dict[str, str]]],
    parser: Callable[[str], Dict[str, Any]],
    stage_caller: StageCaller,
    fallback_stage_caller: Optional[StageCaller],
    stage_recorder: Optional[StageRecorder],
    input_meta: Dict[str, Any],
    max_tokens: int,
) -> Tuple[Dict[str, Any], int, str, str]:
    messages = build_messages()
    last_output = ""
    last_err: Optional[Exception] = None
    for attempt_idx in range(STAGE_GENERATE_ATTEMPTS):
        try:
            res = await stage_caller(stage_name, messages, {"type": "json_object"}, max_tokens)
            last_output = res.output
            parsed = parser(res.output)
            _record_stage_safe(
                stage_recorder,
                stage=stage_name,
                prompt_version=_stage_prompt_version(stage_name),
                status="ok",
                input_json=json.dumps(input_meta, ensure_ascii=False),
                output_json=json.dumps(parsed, ensure_ascii=False),
                error=None,
                ms=res.ms,
                model=res.model,
                backend_override=_stage_backend_from_model(res.model),
            )
            return parsed, res.ms, res.model, res.output
        except Exception as first_err:
            last_err = first_err
            _record_stage_safe(
                stage_recorder,
                stage=stage_name,
                prompt_version=_stage_prompt_version(stage_name),
                status="failed",
                input_json=json.dumps(input_meta, ensure_ascii=False),
                output_json=None,
                error=f"attempt {attempt_idx + 1}/{STAGE_GENERATE_ATTEMPTS}: {type(first_err).__name__}: {first_err}",
                ms=None,
                model=None,
                backend_override=None,
            )
            if last_output:
                try:
                    fix_messages = _build_fix_messages(
                        raw_text=raw_text,
                        bad_output=last_output,
                        template_obj=template_obj,
                        stage_name=stage_name,
                        parse_error=f"{type(first_err).__name__}: {first_err}",
                    )
                    res2 = await stage_caller(f"{stage_name}_repair", fix_messages, {"type": "json_object"}, max_tokens)
                    parsed2 = parser(res2.output)
                    _record_stage_safe(
                        stage_recorder,
                        stage=f"{stage_name}_repair",
                        prompt_version=_stage_prompt_version(f"{stage_name}_repair"),
                        status="ok",
                        input_json=json.dumps(input_meta, ensure_ascii=False),
                        output_json=json.dumps(parsed2, ensure_ascii=False),
                        error=None,
                        ms=res2.ms,
                        model=res2.model,
                        backend_override=_stage_backend_from_model(res2.model),
                    )
                    return parsed2, res2.ms, res2.model, res2.output
                except Exception as second_err:
                    last_err = second_err
                    _record_stage_safe(
                        stage_recorder,
                        stage=f"{stage_name}_repair",
                        prompt_version=_stage_prompt_version(f"{stage_name}_repair"),
                        status="failed",
                        input_json=json.dumps(input_meta, ensure_ascii=False),
                        output_json=None,
                        error=f"attempt {attempt_idx + 1}/{STAGE_GENERATE_ATTEMPTS}: {type(second_err).__name__}: {second_err}",
                        ms=None,
                        model=None,
                        backend_override=None,
                    )

    if fallback_stage_caller is not None:
        return await _run_json_stage(
            stage_name=stage_name,
            title=title,
            raw_text=raw_text,
            template_obj=template_obj,
            build_messages=build_messages,
            parser=parser,
            stage_caller=fallback_stage_caller,
            fallback_stage_caller=None,
            stage_recorder=stage_recorder,
            input_meta=input_meta,
            max_tokens=max_tokens,
        )

    if not last_output:
        raise AnalysisValidationError(f"{stage_name} failed before producing repairable output") from last_err
    raise AnalysisValidationError(f"{stage_name} remained invalid after repair pass") from last_err


async def run_staged_block_analysis(
    *,
    title: str | None,
    raw_text: str,
    stage_caller: StageCaller,
    fallback_stage_caller: Optional[StageCaller] = None,
    stage_recorder: Optional[StageRecorder] = None,
) -> BlockAnalyzeResult:
    text = (raw_text or "").strip()
    if len(text) < MIN_BLOCK_CHARS:
        raise BlockInputError(f"block too short: {len(text)} chars")
    if len(text) > MAX_BLOCK_CHARS:
        raise BlockInputError(f"block too long: {len(text)} chars (max {MAX_BLOCK_CHARS})")
    if _looks_like_noise_block(text):
        raise BlockInputError("block looks like test/log/noise content")

    evidence_template = {"evidence_units": [{"quote": "", "kind": "fact", "topic": ""}], "topic_candidates": [], "entry_shape": "mixed"}
    evidence_obj, evidence_ms, evidence_model, _ = await _run_json_stage(
        stage_name="evidence",
        title=title,
        raw_text=text,
        template_obj=evidence_template,
        build_messages=lambda: _build_evidence_messages(title=title, raw_text=text),
        parser=lambda raw: _parse_evidence_or_raise(raw, raw_text=text),
        stage_caller=stage_caller,
        fallback_stage_caller=fallback_stage_caller,
        stage_recorder=stage_recorder,
        input_meta=_safe_stage_meta(title=title, raw_text=text),
        max_tokens=260,
    )

    deep_template = {
        "main_threads": [],
        "core_conflict": "",
        "core_need": "",
        "behavior_pattern": "",
        "deep_analysis": "",
        "confidence_notes": "",
    }
    deep_obj, deep_ms, deep_model, _ = await _run_json_stage(
        stage_name="deep",
        title=title,
        raw_text=text,
        template_obj=deep_template,
        build_messages=lambda: _build_deep_messages(title=title, raw_text=text, evidence_obj=evidence_obj),
        parser=lambda raw: _parse_deep_or_raise(raw, raw_text=text),
        stage_caller=stage_caller,
        fallback_stage_caller=fallback_stage_caller,
        stage_recorder=stage_recorder,
        input_meta=_safe_stage_meta(title=title, raw_text=text, evidence_obj=evidence_obj),
        max_tokens=420,
    )

    final_template = {
        "summary_1_3": "",
        "open_insight": "",
        "signals": {"mood": None, "stress": None, "sleep": None, "exercise": None, "social": None, "work": None},
        "facts": [],
        "todos": [],
        "topics": [],
        "evidence_spans": [],
        "psychological_themes": [],
        "tensions": [],
        "needs": [],
        "patterns": [],
        "memory_candidates": [],
        "reflection_depth": None,
    }
    final_obj, normalize_ms, normalize_model, raw_output = await _run_json_stage(
        stage_name="normalize",
        title=title,
        raw_text=text,
        template_obj=final_template,
        build_messages=lambda: _build_normalize_messages(title=title, raw_text=text, evidence_obj=evidence_obj, deep_obj=deep_obj),
        parser=_parse_or_raise,
        stage_caller=stage_caller,
        fallback_stage_caller=fallback_stage_caller,
        stage_recorder=stage_recorder,
        input_meta=_safe_stage_meta(title=title, raw_text=text, evidence_obj=evidence_obj, deep_obj=deep_obj),
        max_tokens=PHI_NUM_PREDICT,
    )

    if _has_unwanted_english(obj=final_obj, raw_text=text):
        if stage_recorder:
            stage_recorder(
                stage="validate",
                prompt_version=_stage_prompt_version("validate"),
                status="rejected",
                input_json=json.dumps(_safe_stage_meta(title=title, raw_text=text, evidence_obj=evidence_obj, deep_obj=deep_obj), ensure_ascii=False),
                output_json=json.dumps(final_obj, ensure_ascii=False),
                error="analysis contains unsupported English output for Chinese diary",
                ms=0,
                model=normalize_model,
            )
        raise AnalysisValidationError("analysis contains unsupported English output for Chinese diary")

    final_obj = attach_analysis_quality(final_obj, text)
    quality = final_obj.get("analysis_quality") or {}
    if str(quality.get("band") or "") == "reject":
        if stage_recorder:
            stage_recorder(
                stage="validate",
                prompt_version=_stage_prompt_version("validate"),
                status="rejected",
                input_json=json.dumps(_safe_stage_meta(title=title, raw_text=text, evidence_obj=evidence_obj, deep_obj=deep_obj), ensure_ascii=False),
                output_json=json.dumps(final_obj, ensure_ascii=False),
                error="normalized analysis rejected by quality gate",
                ms=0,
                model=normalize_model,
            )
        raise AnalysisValidationError("normalized analysis rejected by quality gate")

    if stage_recorder:
        stage_recorder(
            stage="final",
            prompt_version=_stage_prompt_version("final"),
            status="ok",
            input_json=json.dumps(_safe_stage_meta(title=title, raw_text=text, evidence_obj=evidence_obj, deep_obj=deep_obj), ensure_ascii=False),
            output_json=json.dumps(final_obj, ensure_ascii=False),
            error=None,
            ms=evidence_ms + deep_ms + normalize_ms,
            model=normalize_model,
        )

    return BlockAnalyzeResult(
        analysis=final_obj,
        ms=evidence_ms + deep_ms + normalize_ms,
        raw_output=raw_output,
    )


async def analyze_block(
    *,
    title: str | None,
    raw_text: str,
    client: OllamaClient,
    stage_recorder: Optional[StageRecorder] = None,
) -> BlockAnalyzeResult:
    async def _call(stage: str, messages: List[Dict[str, str]], response_format: Optional[Dict[str, Any]], max_tokens: int) -> StageCallResult:
        content, ms = await client.chat_text(
            model=PHI_MODEL,
            messages=messages,
            options={"temperature": 0, "top_p": 0.1, "num_predict": max_tokens},
        )
        return StageCallResult(output=content, ms=ms, model=f"local:{PHI_MODEL}")

    return await run_staged_block_analysis(
        title=title,
        raw_text=raw_text,
        stage_caller=_call,
        fallback_stage_caller=None,
        stage_recorder=stage_recorder,
    )
