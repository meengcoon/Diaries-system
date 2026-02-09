from __future__ import annotations

"""pipeline.rollup_entry

Step P0-1: roll up per-block analyses into a single entry_analysis + FTS index.

Why this exists:
  - /api/diary/save only inserts entries + blocks + jobs (no model calls)
  - scripts/run_block_jobs.py produces block_analysis per block
  - retrieval/chat uses entry_analysis + entry_fts, so we must "close the loop"

Design:
  - Pure deterministic rules (no LLM) to keep it fast + stable.
  - Only uses OK block analyses; skipped/failed blocks are reflected in rollup_meta.
  - Safe to call multiple times; output is stable given the same block inputs.
"""

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from storage import db


ROLLUP_MODEL = "rollup"
ROLLUP_PROMPT_VERSION = "rollup_v1"


_SENT_SPLIT_RE = re.compile(r"(?<=[\.!?。！？])\s+")


def _dedupe_stable(items: Iterable[str], *, limit: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        s = str(x or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= int(limit):
            break
    return out


def _merge_signals(block_objs: List[Dict[str, Any]]) -> Dict[str, Optional[int]]:
    """Latest-non-null wins for each signal key."""
    keys = ("mood", "stress", "sleep", "exercise", "social", "work")
    merged: Dict[str, Optional[int]] = {k: None for k in keys}
    for obj in block_objs:
        sig = obj.get("signals")
        if not isinstance(sig, dict):
            continue
        for k in keys:
            v = sig.get(k)
            if isinstance(v, int) and 0 <= v <= 10:
                merged[k] = v
            elif v is None:
                # do not overwrite an existing number
                continue
    return merged


def _merge_reflection_depth(block_objs: List[Dict[str, Any]]) -> Optional[int]:
    vals: List[int] = []
    for obj in block_objs:
        v = obj.get("reflection_depth")
        if isinstance(v, int) and 0 <= v <= 3:
            vals.append(v)
    return max(vals) if vals else None


def _merge_summary(block_objs: List[Dict[str, Any]], *, max_sentences: int = 3, max_chars: int = 480) -> str:
    parts: List[str] = []
    for obj in block_objs:
        s = str(obj.get("summary_1_3") or "").strip()
        if s:
            parts.append(s)

    if not parts:
        return "Summary not provided"

    joined = " ".join(parts)
    # Prefer sentence-based truncation; fall back to char cap.
    sents = [x.strip() for x in _SENT_SPLIT_RE.split(joined) if x.strip()]
    if sents:
        joined = " ".join(sents[: int(max_sentences)])
    if len(joined) > int(max_chars):
        joined = joined[: int(max_chars)].rstrip() + "…"
    return joined


def rollup_entry_from_blocks(
    entry_id: int,
    *,
    max_topics: int = 6,
    max_facts: int = 10,
    max_todos: int = 10,
) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """Build entry-level analysis_obj from per-block analyses.

    Returns: (analysis_obj, rollup_meta)
    """

    rows = db.list_entry_blocks_with_analysis(int(entry_id))
    if not rows:
        meta = {"blocks_total": 0, "blocks_ok": 0, "blocks_skipped": 0, "blocks_failed": 0}
        return (
            {
                "summary_1_3": "Summary not provided",
                "signals": {"mood": None, "stress": None, "sleep": None, "exercise": None, "social": None, "work": None},
                "facts": [],
                "todos": [],
                "topics": [],
                "evidence_spans": [],
                "reflection_depth": None,
                "rollup_meta": meta,
            },
            meta,
        )

    blocks_total = len(rows)
    blocks_ok = blocks_skipped = blocks_failed = 0

    ok_objs: List[Dict[str, Any]] = []
    topics_all: List[str] = []
    facts_all: List[str] = []
    todos_all: List[str] = []
    evidence_all: List[str] = []

    for r in rows:
        job_status = (r.get("job_status") or "").strip()
        if job_status == "skipped":
            blocks_skipped += 1
        elif job_status == "failed":
            blocks_failed += 1

        ok_flag = r.get("analysis_ok")
        if int(ok_flag or 0) != 1:
            continue

        obj = db._safe_json_loads(r.get("analysis_json") or "{}") or {}
        if not isinstance(obj, dict):
            continue

        blocks_ok += 1
        ok_objs.append(obj)
        topics_all.extend(obj.get("topics") or [])
        facts_all.extend(obj.get("facts") or [])
        todos_all.extend(obj.get("todos") or [])
        evidence_all.extend(obj.get("evidence_spans") or [])

    # Stable, deterministic merges
    analysis_obj: Dict[str, Any] = {
        "summary_1_3": _merge_summary(ok_objs),
        "signals": _merge_signals(ok_objs),
        "facts": _dedupe_stable(facts_all, limit=max_facts),
        "todos": _dedupe_stable(todos_all, limit=max_todos),
        "topics": _dedupe_stable(topics_all, limit=max_topics),
        "evidence_spans": _dedupe_stable(evidence_all, limit=12),
        "reflection_depth": _merge_reflection_depth(ok_objs),
    }

    meta = {
        "blocks_total": int(blocks_total),
        "blocks_ok": int(blocks_ok),
        "blocks_skipped": int(blocks_skipped),
        "blocks_failed": int(blocks_failed),
    }
    analysis_obj["rollup_meta"] = meta
    return analysis_obj, meta


def persist_entry_rollup(entry_id: int) -> Dict[str, Any]:
    """Compute + persist entry_analysis and FTS for one entry."""
    analysis_obj, meta = rollup_entry_from_blocks(int(entry_id))
    db.save_entry_analysis(
        entry_id=int(entry_id),
        analysis_json=json.dumps(analysis_obj, ensure_ascii=False),
        model=ROLLUP_MODEL,
        prompt_version=ROLLUP_PROMPT_VERSION,
    )
    db.upsert_entry_fts(entry_id=int(entry_id), analysis_obj=analysis_obj)
    return {"entry_id": int(entry_id), "rollup_meta": meta}
