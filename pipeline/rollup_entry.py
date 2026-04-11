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

from storage.db_core import _safe_json_loads, compute_sha256
from storage.repo_entries import get_entry, save_entry_analysis
from storage.repo_fts import upsert_entry_fts
from storage.repo_jobs import list_entry_blocks_with_analysis
from pipeline.analysis_quality import attach_analysis_quality, insufficient_analysis_quality


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


def _dedupe_sentences(text: str, *, max_sentences: int, max_chars: int) -> str:
    sents = [x.strip() for x in _SENT_SPLIT_RE.split(str(text or "").strip()) if x.strip()]
    if not sents:
        cleaned = str(text or "").strip()
        return cleaned[: int(max_chars)].rstrip() + ("…" if len(cleaned) > int(max_chars) else "")
    deduped = _dedupe_stable(sents, limit=max_sentences)
    joined = " ".join(deduped)
    if len(joined) > int(max_chars):
        joined = joined[: int(max_chars)].rstrip() + "…"
    return joined


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

    return _dedupe_sentences(" ".join(parts), max_sentences=max_sentences, max_chars=max_chars)


def _merge_open_insight(block_objs: List[Dict[str, Any]], *, max_sentences: int = 6, max_chars: int = 900) -> str:
    parts: List[str] = []
    for obj in block_objs:
        s = str(obj.get("open_insight") or "").strip()
        if s:
            parts.append(s)

    if not parts:
        return "暂无更深入的开放洞察。"

    return _dedupe_sentences(" ".join(parts), max_sentences=max_sentences, max_chars=max_chars)


def _looks_like_noise_entry(raw_text: str, *, blocks_total: int, blocks_skipped: int) -> bool:
    s = str(raw_text or "").lower()
    markers = (
        "smoke_frontend_api",
        "debug save fields",
        "write to storage db check",
        "append-test",
        "sqlite entry",
        "selfcheck:",
    )
    marker_hits = sum(s.count(marker) for marker in markers)
    timestamp_hits = len(re.findall(r"---\s*\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}", s))
    if marker_hits >= 3:
        return True
    if marker_hits >= 1 and timestamp_hits >= 3:
        return True
    if blocks_total >= 8 and blocks_skipped / max(1, blocks_total) >= 0.6 and marker_hits >= 1:
        return True
    return False


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

    rows = list_entry_blocks_with_analysis(int(entry_id))
    if not rows:
        meta = {"blocks_total": 0, "blocks_ok": 0, "blocks_skipped": 0, "blocks_failed": 0}
        analysis_obj = {
            "summary_1_3": "内容不足，未生成有效分析。",
            "open_insight": "当前条目没有可供分析的有效内容。",
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
            "rollup_meta": meta,
            "analysis_quality": insufficient_analysis_quality(reason="没有可分析的 block。"),
        }
        return (analysis_obj, meta)

    blocks_total = len(rows)
    blocks_ok = blocks_skipped = blocks_failed = 0
    raw_texts: List[str] = []
    all_raw_texts: List[str] = []

    ok_objs: List[Dict[str, Any]] = []
    topics_all: List[str] = []
    facts_all: List[str] = []
    todos_all: List[str] = []
    evidence_all: List[str] = []

    for r in rows:
        job_status = (r.get("job_status") or "").strip()
        raw_text = str(r.get("raw_text") or "")
        all_raw_texts.append(raw_text)
        if job_status == "skipped":
            blocks_skipped += 1
        elif job_status == "failed":
            blocks_failed += 1

        ok_flag = r.get("analysis_ok")
        if int(ok_flag or 0) != 1:
            continue

        obj = _safe_json_loads(r.get("analysis_json") or "{}") or {}
        if not isinstance(obj, dict):
            continue
        obj = attach_analysis_quality(obj, raw_text)
        raw_texts.append(raw_text)

        blocks_ok += 1
        ok_objs.append(obj)
        topics_all.extend(obj.get("topics") or [])
        facts_all.extend(obj.get("facts") or [])
        todos_all.extend(obj.get("todos") or [])
        evidence_all.extend(obj.get("evidence_spans") or [])

    # Stable, deterministic merges
    analysis_obj: Dict[str, Any] = {
        "summary_1_3": _merge_summary(ok_objs),
        "open_insight": _merge_open_insight(ok_objs),
        "signals": _merge_signals(ok_objs),
        "facts": _dedupe_stable(facts_all, limit=max_facts),
        "todos": _dedupe_stable(todos_all, limit=max_todos),
        "topics": _dedupe_stable(topics_all, limit=max_topics),
        "evidence_spans": _dedupe_stable(evidence_all, limit=12),
        "psychological_themes": _dedupe_stable(
            [x for obj in ok_objs for x in (obj.get("psychological_themes") or [])],
            limit=8,
        ),
        "tensions": _dedupe_stable(
            [x for obj in ok_objs for x in (obj.get("tensions") or [])],
            limit=8,
        ),
        "needs": _dedupe_stable(
            [x for obj in ok_objs for x in (obj.get("needs") or [])],
            limit=8,
        ),
        "patterns": _dedupe_stable(
            [x for obj in ok_objs for x in (obj.get("patterns") or [])],
            limit=8,
        ),
        "memory_candidates": _dedupe_stable(
            [x for obj in ok_objs for x in (obj.get("memory_candidates") or [])],
            limit=8,
        ),
        "reflection_depth": _merge_reflection_depth(ok_objs),
    }

    meta = {
        "blocks_total": int(blocks_total),
        "blocks_ok": int(blocks_ok),
        "blocks_skipped": int(blocks_skipped),
        "blocks_failed": int(blocks_failed),
    }
    joined_all_raw = "\n".join(all_raw_texts)
    joined_raw = "\n".join(raw_texts)
    if _looks_like_noise_entry(joined_all_raw, blocks_total=blocks_total, blocks_skipped=blocks_skipped):
        analysis_obj = {
            "summary_1_3": "内容不足，未生成有效分析。",
            "open_insight": "当前条目主要由测试日志、调试痕迹或分隔文本组成，因此不作为有效日记分析。",
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
            "analysis_quality": insufficient_analysis_quality(reason="条目整体更像测试日志/调试文本，未进入有效分析。"),
        }
    elif blocks_ok <= 0:
        analysis_obj = {
            "summary_1_3": "内容不足，未生成有效分析。",
            "open_insight": "当前条目中的内容过短、过碎或主要为测试/分隔文本，因此被跳过。",
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
            "analysis_quality": insufficient_analysis_quality(reason="所有 block 都被跳过，未进入有效分析。"),
        }
    else:
        analysis_obj = attach_analysis_quality(analysis_obj, joined_raw)
    analysis_obj["rollup_meta"] = meta
    return analysis_obj, meta


def persist_entry_rollup(entry_id: int, *, expected_entry_version: Optional[int] = None) -> Dict[str, Any]:
    """Compute + persist entry_analysis and FTS for one entry."""
    entry = get_entry(int(entry_id))
    if not entry:
        return {"entry_id": int(entry_id), "ignored_stale": True, "reason": "entry_missing"}
    current_entry_version = int(entry.get("version") or 0)
    if expected_entry_version is not None and current_entry_version != int(expected_entry_version):
        return {
            "entry_id": int(entry_id),
            "entry_version": current_entry_version,
            "expected_entry_version": int(expected_entry_version),
            "ignored_stale": True,
            "reason": "stale_entry_version",
        }
    analysis_obj, meta = rollup_entry_from_blocks(int(entry_id))
    analysis_hash = compute_sha256(json.dumps(analysis_obj, ensure_ascii=False, sort_keys=True))
    save_entry_analysis(
        entry_id=int(entry_id),
        analysis_json=json.dumps(analysis_obj, ensure_ascii=False),
        model=ROLLUP_MODEL,
        prompt_version=ROLLUP_PROMPT_VERSION,
        entry_version=current_entry_version,
        analysis_hash=analysis_hash,
    )
    upsert_entry_fts(entry_id=int(entry_id), analysis_obj=analysis_obj)
    return {
        "entry_id": int(entry_id),
        "entry_version": current_entry_version,
        "analysis_hash": analysis_hash,
        "rollup_meta": meta,
    }
