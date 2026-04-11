from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks

from .analysis_config import analysis_primary_backend, normalize_provider
from .analysis_jobs import prioritize_entry_jobs
from .analysis_runner import (
    BLOCK_ANALYZE_PROC_LOCK as _BLOCK_ANALYZE_PROC_LOCK,
    detail_should_fallback_to_local,
    log_subprocess_result,
    run_analyze_entry_bg,
    run_analyze_latest_bg,
    run_python_cli,
    should_fallback_to_local,
)


def queue_entry_analysis(
    background_tasks: BackgroundTasks,
    *,
    base_dir: Path,
    entry_id: int,
    preferred_provider: str,
    max_attempts: int,
    job_timeout_s: int,
    force_reanalyze: bool,
) -> None:
    background_tasks.add_task(
        run_analyze_entry_bg,
        base_dir=base_dir,
        entry_id=int(entry_id),
        preferred_provider=normalize_provider(preferred_provider),
        max_attempts=max(1, int(max_attempts)),
        job_timeout_s=max(10, int(job_timeout_s)),
        force_reanalyze=bool(force_reanalyze),
    )
