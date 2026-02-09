# pipeline/ingest.py
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from core.settings import PHI_MODEL, PROMPT_VERSION_ENTRY
from utils.timeutil import utc_now_iso

# Step 1: split a diary entry into blocks (no model calls on save)
from .segment import split_to_blocks


# DB helper（按你项目实际 import 路径调整）
try:
    from storage.db import insert_entry, insert_entry_block, insert_block_job
except ImportError:
    from db import insert_entry, insert_entry_block, insert_block_job  # type: ignore


PROMPT_VERSION = PROMPT_VERSION_ENTRY

MAX_CHARS = 8000

# Second-pass filter (insurance) before enqueueing jobs.
_SEPARATOR_ONLY_RE = re.compile(r"^[\s\-_=*~`]+$")


class InputError(ValueError):
    pass


def _now_iso() -> str:
    return utc_now_iso()


def _is_separator_only(s: str) -> bool:
    t = (s or "").strip()
    return bool(t) and bool(_SEPARATOR_ONLY_RE.match(t))


def _filter_blocks_for_jobs(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop empty/separator-only blocks and merge ultra-short tails into previous.

    This keeps job queue clean and reduces pointless retries.
    """

    out: List[Dict[str, Any]] = []
    for b in (blocks or []):
        # Compatibility: segment.split_to_blocks() returns "text";
        # some older code paths used "raw_text".
        raw = str(b.get("raw_text") or b.get("text") or "").strip()
        if not raw or _is_separator_only(raw):
            continue
        # Normalize for downstream insert/read logic.
        b["raw_text"] = raw
        out.append(b)

    # re-index
    for i, b in enumerate(out):
        b["idx"] = i
    return out


@dataclass
class IngestResult:
    ok: bool
    entry_id: int
    analysis_ok: bool
    prompt_version: str
    model: str
    insert_ms: int
    extract_ms: int
    error: str | None = None


async def ingest_entry(*, text: str, source: str = "api") -> Dict[str, Any]:
    """Save raw entry, split into blocks, enqueue block jobs.

    Hard rule (Step 1 / M1): NO model calls on save.
    All analysis happens later in idle worker (run_block_jobs.py).
    """

    if text is None or not str(text).strip():
        raise InputError("empty text is not allowed")
    text = str(text).strip()
    if len(text) > MAX_CHARS:
        raise InputError(f"text too long: {len(text)} chars (max {MAX_CHARS})")

    # Insert entry
    t0 = time.perf_counter()
    created_at = _now_iso()
    entry_id = insert_entry(raw_text=text, created_at=created_at, source=source)
    insert_ms = int((time.perf_counter() - t0) * 1000)

    # Split -> blocks -> jobs
    t1 = time.perf_counter()
    blocks = _filter_blocks_for_jobs(split_to_blocks(text))
    block_ids: List[int] = []
    now = _now_iso()

    for b in blocks:
        block_id = insert_entry_block(
            entry_id=int(entry_id),
            idx=int(b.get("idx", 0)),
            title=(b.get("title") or None),
            raw_text=str(b.get("raw_text") or b.get("text") or ""),
            created_at=created_at,
        )
        if block_id:
            block_ids.append(int(block_id))
            insert_block_job(
                block_id=int(block_id),
                status="pending",
                attempts=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )

    enqueue_ms = int((time.perf_counter() - t1) * 1000)

    # Keep old keys for backward compatibility, but signal that analysis did NOT run.
    res = IngestResult(
        ok=True,
        entry_id=int(entry_id),
        analysis_ok=False,
        prompt_version=PROMPT_VERSION,
        model=PHI_MODEL,  # "analysis model" (not used on save; kept for compatibility)
        insert_ms=insert_ms,
        extract_ms=0,
        error=None,
    ).__dict__
    res.update({"queued_blocks": len(block_ids), "block_ids": block_ids, "enqueue_ms": enqueue_ms})
    return res
