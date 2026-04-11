from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from retrieval.fts import search_entries_brief
from storage.repo_entries import list_recent_entry_summaries
from storage.repo_mem import list_mem_cards

SCHEMA_VERSION = "context_pack_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def _pack_chars(obj: Any) -> int:
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return len(str(obj))


def _model_view(pack: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema": pack.get("schema"),
        "created_at": pack.get("created_at"),
        "query": pack.get("query"),
        "limits": pack.get("limits"),
        "recent": pack.get("recent"),
        "topk": pack.get("topk"),
        "mem_cards": pack.get("mem_cards"),
    }


def _model_chars(pack: Dict[str, Any]) -> int:
    return _pack_chars(_model_view(pack))


def _topic_set_from_entries(entries: List[Dict[str, Any]]) -> List[str]:
    topics: List[str] = []
    seen = set()
    for e in entries:
        ts = e.get("topics") or []
        if not isinstance(ts, list):
            continue
        for t in ts:
            topic = str(t).strip()
            if not topic or topic in seen:
                continue
            seen.add(topic)
            topics.append(topic)
    return topics


def _score_card(topics: List[str], card_content: Dict[str, Any]) -> int:
    ct = card_content.get("topics") or []
    if not isinstance(ct, list):
        ct = []
    s1 = {str(x).strip() for x in topics if str(x).strip()}
    s2 = {str(x).strip() for x in ct if str(x).strip()}
    return len(s1 & s2)


def _select_mem_cards_by_topics(
    *,
    topics: List[str],
    pool: int = 30,
    top_m: int = 8,
) -> List[Dict[str, Any]]:
    rows = list_mem_cards(limit=int(pool))

    scored: List[Tuple[int, str, str, Dict[str, Any], Dict[str, Any]]] = []
    for r in rows:
        content = _safe_json_loads(r.get("content_json", "")) or {}
        if not isinstance(content, dict):
            content = {}
        score = _score_card(topics, content)
        scored.append(
            (
                int(score),
                str(r.get("updated_at") or ""),
                str(r.get("card_id") or ""),
                r,
                content,
            )
        )

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    out: List[Dict[str, Any]] = []
    for score, _updated_at, _card_id, r, content in scored:
        if len(out) >= int(top_m):
            break
        if int(score) <= 0:
            continue
        out.append(
            {
                "card_id": r.get("card_id"),
                "type": r.get("type"),
                "updated_at": r.get("updated_at"),
                "confidence": r.get("confidence"),
                "score": int(score),
                "content": content,
            }
        )
    return out


def _trim_entry_fields(entries: List[Dict[str, Any]], *, drop_facts: bool, drop_todos: bool) -> None:
    for e in entries:
        if drop_facts:
            e["facts"] = []
        if drop_todos:
            e["todos"] = []


def build_context_pack(
    query: str,
    *,
    top_k: int = 6,
    recent_n: int = 8,
    mem_pool: int = 30,
    mem_top_m: int = 8,
    char_budget: int = 5000,
) -> Dict[str, Any]:
    t0 = time.perf_counter()

    q = (query or "").strip()
    recent = list_recent_entry_summaries(int(recent_n))
    topk_entries = search_entries_brief(q, top_k=int(top_k)) if q else []

    topics = _topic_set_from_entries(topk_entries)
    mem_cards = _select_mem_cards_by_topics(topics=topics, pool=int(mem_pool), top_m=int(mem_top_m))

    pack: Dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "created_at": _now_iso(),
        "query": q,
        "limits": {
            "top_k": int(top_k),
            "recent_n": int(recent_n),
            "mem_pool": int(mem_pool),
            "mem_top_m": int(mem_top_m),
            "char_budget": int(char_budget),
        },
        "recent": recent,
        "topk": topk_entries,
        "mem_cards": mem_cards,
        "meta": {
            "build_ms": 0,
            "truncated": False,
            "steps": [],
            "initial_counts": {
                "recent": len(recent),
                "topk": len(topk_entries),
                "mem_cards": len(mem_cards),
            },
            "initial_chars": 0,
        },
    }

    steps: List[str] = []
    pack["meta"]["initial_chars"] = _model_chars(pack)

    def over_budget() -> bool:
        return _model_chars(pack) > int(char_budget)

    if over_budget() and pack.get("topk"):
        _trim_entry_fields(pack["topk"], drop_facts=True, drop_todos=True)
        steps.append("drop_topk_facts_todos")

    while over_budget() and len(pack.get("recent") or []) > 1:
        pack["recent"] = (pack.get("recent") or [])[:-1]
        steps.append("shrink_recent")

    while over_budget() and len(pack.get("topk") or []) > 1:
        pack["topk"] = (pack.get("topk") or [])[:-1]
        steps.append("shrink_topk")

    def min_mem_cards() -> int:
        return 1 if len(mem_cards) > 0 else 0

    while over_budget() and len(pack.get("mem_cards") or []) > min_mem_cards():
        pack["mem_cards"] = (pack.get("mem_cards") or [])[:-1]
        steps.append("shrink_mem_cards")

    if over_budget() and len(pack.get("mem_cards") or []) > 0:
        pack["mem_cards"] = []
        steps.append("drop_mem_cards")
    if over_budget() and len(pack.get("topk") or []) > 0:
        pack["topk"] = []
        steps.append("drop_topk")
    if over_budget() and len(pack.get("recent") or []) > 0:
        pack["recent"] = []
        steps.append("drop_recent")

    ms = int((time.perf_counter() - t0) * 1000)
    pack["meta"]["build_ms"] = ms
    pack["meta"]["truncated"] = bool(steps)
    pack["meta"]["steps"] = steps
    pack["meta"]["final_chars_model"] = _model_chars(pack)
    pack["meta"]["final_chars_total"] = _pack_chars(pack)
    return pack


def build_context_pack_text(pack: Dict[str, Any]) -> str:
    return json.dumps(_model_view(pack), ensure_ascii=False, sort_keys=True)


def build_context_pack_debug_text(pack: Dict[str, Any]) -> str:
    return json.dumps(pack, ensure_ascii=False, sort_keys=True)
