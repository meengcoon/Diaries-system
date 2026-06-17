from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .analysis_config import analysis_primary_backend, normalize_provider
from .analysis_runner import enqueue_entry_analysis, enqueue_latest_analysis


def queue_entry_analysis(
    *,
    base_dir: Path,
    entry_id: int,
    preferred_provider: str,
    max_attempts: int,
    job_timeout_s: int,
    force_reanalyze: bool,
) -> Dict[str, Any]:
    return enqueue_entry_analysis(
        base_dir=base_dir,
        entry_id=int(entry_id),
        preferred_provider=normalize_provider(preferred_provider),
        max_attempts=max(1, int(max_attempts)),
        job_timeout_s=max(10, int(job_timeout_s)),
        force_reanalyze=bool(force_reanalyze),
    )


def queue_latest_analysis(
    *,
    base_dir: Path,
    entry_limit: int,
    job_limit: int,
    preferred_provider: str,
    min_block_chars: int,
    max_attempts: int,
    job_timeout_s: int,
) -> Dict[str, Any]:
    return enqueue_latest_analysis(
        base_dir=base_dir,
        entry_limit=max(1, int(entry_limit)),
        job_limit=max(1, int(job_limit)),
        preferred_provider=normalize_provider(preferred_provider),
        min_block_chars=max(1, int(min_block_chars)),
        max_attempts=max(1, int(max_attempts)),
        job_timeout_s=max(10, int(job_timeout_s)),
    )
