from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from storage.db import get_mem_card, insert_mem_card_change, list_mem_cards, upsert_mem_card
from core.settings import MEM_UPDATE_MODEL as DEFAULT_PHI_MODEL, PROMPT_VERSION_MEM_UPDATE

PROMPT_VERSION = PROMPT_VERSION_MEM_UPDATE

# If your project has an Ollama client, we will use it. Otherwise we fall back deterministically.
try:
    from llm.ollama_client import OllamaClient
except ImportError:  # pragma: no cover
    OllamaClient = None  # type: ignore

try:
    from bot.generation_router import generate as routed_generate
except Exception:  # pragma: no cover
    routed_generate = None  # type: ignore



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _should_use_cloud_mem_update() -> bool:
    # Default cloud-first if CLOUD_ENABLED=1.
    if _env_bool("MEM_UPDATE_FORCE_LOCAL", False):
        return False
    if "MEM_UPDATE_FORCE_CLOUD" in os.environ:
        return _env_bool("MEM_UPDATE_FORCE_CLOUD", True)
    return _env_bool("CLOUD_ENABLED", False)


def _should_use_local_mem_llm() -> bool:
    # Default OFF to avoid local model pressure when cloud is enabled.
    return _env_bool("MEM_UPDATE_USE_LOCAL_LLM", False)


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", s)
    return s[:80] if s else "general"


def _merge_patch(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow+recursive JSON merge.

    - dict merges recursively
    - None deletes a key
    """
    out = dict(base or {})
    for k, v in (patch or {}).items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge_patch(out.get(k, {}), v)
        else:
            out[k] = v
    return out


def _score_candidate(entry_topics: List[str], card_content: Dict[str, Any]) -> int:
    ct = card_content.get("topics") or []
    if not isinstance(ct, list):
        ct = []
    s1 = set([str(x).strip() for x in entry_topics if str(x).strip()])
    s2 = set([str(x).strip() for x in ct if str(x).strip()])
    return len(s1 & s2)


def pick_candidates(analysis_json: Dict[str, Any], *, top_n: int = 5, pool: int = 30) -> List[Dict[str, Any]]:
    """Pick Top-N cards from a small pool; never scan all cards."""
    topics = analysis_json.get("topics") or []
    if not isinstance(topics, list):
        topics = []
    entry_topics = [str(x) for x in topics]

    rows = list_mem_cards(limit=pool)
    scored: List[Tuple[int, Dict[str, Any], Dict[str, Any]]] = []
    for r in rows:
        content = _safe_json_loads(r.get("content_json", "")) or {}
        scored.append((_score_candidate(entry_topics, content), r, content))

    scored.sort(key=lambda x: (x[0], x[1].get("updated_at", "")), reverse=True)

    out: List[Dict[str, Any]] = []
    for score, r, content in scored[:top_n]:
        out.append(
            {
                "card_id": r["card_id"],
                "type": r["type"],
                "content": content,
                "confidence": r.get("confidence"),
                "score": score,
            }
        )
    return out


def _build_phi_messages(analysis_json: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Short, strict JSON-in/JSON-out prompt for Phi."""
    payload = {
        "entry": {
            "summary_1_3": analysis_json.get("summary_1_3"),
            "topics": analysis_json.get("topics"),
            "facts": analysis_json.get("facts"),
            "todos": analysis_json.get("todos"),
            "signals": analysis_json.get("signals"),
        },
        "candidates": [
            {"card_id": c["card_id"], "type": c["type"], "content": c["content"]} for c in candidates
        ],
        "rules": [
            "Return ONLY valid JSON.",
            'Output schema: {"ops": [...]}',
            "Each op: {op: update|create, card_id?, type, merge_patch?, content_json?, confidence, note}",
            "Only update cards from candidates (card_id must be one of candidates).",
            "At most 2 ops.",
            "Prefer update over create.",
            "Keep merge_patch minimal.",
        ],
        "prompt_version": PROMPT_VERSION,
    }

    system = (
        "You are a strict JSON engine for long-term memory updates. "
        "Return a single JSON object and nothing else."
    )
    user = json.dumps(payload, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_json_repair_messages(bad_json_text: str) -> List[Dict[str, str]]:
    """One-shot repair: rewrite malformed output into valid JSON (same schema)."""
    system = (
        "You are a strict JSON repair engine. "
        "Output ONLY a single valid JSON object and nothing else. "
        "No explanations."
    )
    payload = {
        "task": "repair_json",
        "rules": [
            "Return ONLY valid JSON.",
            "Top-level must be an object with key 'ops' (list).",
            "If you cannot recover, return {\"ops\": []}.",
        ],
        "input": bad_json_text,
        "prompt_version": PROMPT_VERSION,
    }
    user = json.dumps(payload, ensure_ascii=False)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]




def _extract_first_json_obj(text: str) -> str:
    if not text:
        return text
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return text.strip()
    return text[s : e + 1].strip()


def _fallback_ops(entry_id: int, analysis_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    topics = analysis_json.get("topics") or []
    if isinstance(topics, list) and topics:
        primary = str(topics[0])
    else:
        primary = "general"

    card_id = f"topic:{_slug(primary)}"

    # Minimal patch: keep it small, avoid growing context.
    patch = {
        "topics": topics if isinstance(topics, list) else [primary],
        "last_entry_id": entry_id,
        "last_summary": analysis_json.get("summary_1_3"),
        "facts_latest": analysis_json.get("facts") or [],
        "todos_latest": analysis_json.get("todos") or [],
    }

    return [
        {
            "op": "update",
            "card_id": card_id,
            "type": "topic",
            "merge_patch": patch,
            "confidence": 0.6,
            "note": "fallback_topic_card",
        }
    ]


async def update_mem_cards(
    *,
    entry_id: int,
    analysis_json: Dict[str, Any],
    client: Optional[Any] = None,
    model: Optional[str] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """M2: partial update of mem_cards + audit log.

    Guarantees:
    - Only updates Top-N candidate cards (or deterministic fallback card when no candidates exist)
    - Every update/create writes a mem_card_changes row with before/patch/after (or before/after)
    """

    t0 = time.perf_counter()
    model = model or DEFAULT_PHI_MODEL

    candidates = pick_candidates(analysis_json, top_n=top_n)
    allowed_update_ids = set([c["card_id"] for c in candidates])

    ops: List[Dict[str, Any]] = []
    err: Optional[str] = None

    messages = _build_phi_messages(analysis_json, candidates)

    # 1) Cloud-first path (DeepSeek/Qwen via generation_router), preferred for low local load.
    if _should_use_cloud_mem_update() and routed_generate is not None:
        try:
            preferred_provider = (os.getenv("MEM_UPDATE_PROVIDER") or "deepseek").strip().lower()
            if preferred_provider not in {"deepseek", "qwen"}:
                preferred_provider = "deepseek"

            cloud_payload: Dict[str, Any] = {
                "intent": "long_write",
                "prompt_version": PROMPT_VERSION,
                "force_cloud": True,
                "fallback_backend": "none",
                "preferred_provider": preferred_provider,
                "privacy_level": "L1",
                "is_idle": True,
                "local_model": model,
            }
            cloud_model = (os.getenv("MEM_UPDATE_CLOUD_MODEL") or "").strip()
            if cloud_model:
                cloud_payload["cloud_model"] = cloud_model

            res = await asyncio.to_thread(
                routed_generate,
                task="mem_update",
                payload=cloud_payload,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=500,
            )
            raw = _extract_first_json_obj(str(res.content or ""))
            obj = json.loads(raw)
            cloud_ops = obj.get("ops") if isinstance(obj, dict) else None
            ops = cloud_ops if isinstance(cloud_ops, list) else []
        except Exception as e:
            err = f"cloud_failed: {e}"
            ops = []

    # 2) Optional local LLM path (disabled by default).
    if not ops and _should_use_local_mem_llm():
        try:
            if client is None and OllamaClient is not None:
                client = OllamaClient()
            if client is not None and hasattr(client, "chat_text"):
                text, _ms = await client.chat_text(
                    model=model,
                    messages=messages,
                    options={"temperature": 0, "top_p": 0.1, "num_predict": 500},
                )
                raw = _extract_first_json_obj(text)
                try:
                    obj = json.loads(raw)
                except Exception:
                    # One repair attempt for malformed JSON.
                    repair_messages = _build_json_repair_messages(raw)
                    repaired, _ms2 = await client.chat_text(
                        model=model,
                        messages=repair_messages,
                        options={"temperature": 0, "top_p": 0.1, "num_predict": 400},
                    )
                    obj = json.loads(_extract_first_json_obj(repaired))

                local_ops = obj.get("ops") if isinstance(obj, dict) else None
                ops = local_ops if isinstance(local_ops, list) else []
        except Exception as e:
            if err:
                err = f"{err}; local_failed: {e}"
            else:
                err = f"local_failed: {e}"

    if not ops:
        ops = _fallback_ops(entry_id, analysis_json)

    updated = 0
    changes = 0
    touched: List[str] = []

    for op in ops[:2]:
        op_type = str(op.get("op") or "").strip()
        ctype = str(op.get("type") or "general").strip()
        conf = float(op.get("confidence") or 0.5)

        if op_type == "create":
            # Keep deterministic-ish: require explicit card_id? If not provided, skip create.
            # (Avoid accidental uncontrolled growth of cards.)
            card_id = str(op.get("card_id") or "").strip()
            if not card_id:
                continue
            after = op.get("content_json") or {}
            upsert_mem_card(card_id=card_id, type=ctype, content_json=after, updated_at=_now_iso(), confidence=conf)
            insert_mem_card_change(
                card_id=card_id,
                entry_id=entry_id,
                diff_json={
                    "before": None,
                    "after": after,
                    "meta": {"op": "create", "note": op.get("note"), "prompt_version": PROMPT_VERSION},
                },
                created_at=_now_iso(),
            )
            updated += 1
            changes += 1
            touched.append(card_id)
            continue

        if op_type == "update":
            card_id = str(op.get("card_id") or "").strip()
            if not card_id:
                continue

            # Enforce: update must be in candidates OR be our fallback topic card
            note = str(op.get("note") or "")
            if card_id not in allowed_update_ids and not note.startswith("fallback"):
                continue

            existing = get_mem_card(card_id)
            before = _safe_json_loads(existing.get("content_json", "")) if existing else {}
            patch = op.get("merge_patch") or {}
            after = _merge_patch(before or {}, patch)

            upsert_mem_card(card_id=card_id, type=ctype, content_json=after, updated_at=_now_iso(), confidence=conf)
            insert_mem_card_change(
                card_id=card_id,
                entry_id=entry_id,
                diff_json={
                    "before": before,
                    "patch": patch,
                    "after": after,
                    "meta": {"op": "update", "note": op.get("note"), "prompt_version": PROMPT_VERSION},
                },
                created_at=_now_iso(),
            )
            updated += 1
            changes += 1
            touched.append(card_id)

    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "updated": updated,
        "changes": changes,
        "card_ids": touched,
        "candidates": len(candidates),
        "prompt_version": PROMPT_VERSION,
        "ms": ms,
        "error": err,
    }


async def update_mem_cards_for_entry(
    *,
    entry_id: int,
    entry_analysis: Dict[str, Any],
    client: Optional[Any] = None,
    model: Optional[str] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Compatibility wrapper for scripts that call update_mem_cards_for_entry."""
    return await update_mem_cards(
        entry_id=int(entry_id),
        analysis_json=entry_analysis if isinstance(entry_analysis, dict) else {},
        client=client,
        model=model,
        top_n=int(top_n),
    )
