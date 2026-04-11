from __future__ import annotations

from typing import Any, Dict, List, Optional

from pipeline.ingest import _filter_blocks_for_jobs
from pipeline.segment import split_to_blocks
from storage.repo_jobs import replace_entry_blocks_and_jobs_atomic


def prepare_entry_blocks(raw_text: str) -> List[Dict[str, Any]]:
    text = raw_text or ""
    return _filter_blocks_for_jobs(split_to_blocks(text))


def replace_entry_content_atomic(
    *,
    entry_id: int,
    raw_text: str,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    blocks = prepare_entry_blocks(raw_text)
    return replace_entry_blocks_and_jobs_atomic(
        entry_id=int(entry_id),
        raw_text=raw_text,
        blocks=blocks,
        created_at=created_at,
    )
