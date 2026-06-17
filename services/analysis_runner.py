from __future__ import annotations

import io
import logging
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict

from .analysis_jobs import prioritize_entry_jobs

logger = logging.getLogger(__name__)


def enqueue_entry_analysis(
    *,
    base_dir: Path,
    entry_id: int,
    preferred_provider: str,
    max_attempts: int,
    job_timeout_s: int,
    force_reanalyze: bool = False,
) -> Dict[str, Any]:
    del base_dir, preferred_provider, job_timeout_s
    pending_n = prioritize_entry_jobs(
        int(entry_id),
        force_reanalyze=bool(force_reanalyze),
        max_attempts=max(1, int(max_attempts)),
    )
    return {
        "ok": True,
        "queued": pending_n > 0,
        "entry_id": int(entry_id),
        "pending_jobs": int(pending_n),
        "force_reanalyze": bool(force_reanalyze),
    }


def enqueue_latest_analysis(
    *,
    base_dir: Path,
    entry_limit: int,
    job_limit: int,
    preferred_provider: str,
    min_block_chars: int,
    max_attempts: int,
    job_timeout_s: int,
) -> Dict[str, Any]:
    del preferred_provider, max_attempts, job_timeout_s, job_limit
    old_env = os.environ.get("MIN_BLOCK_CHARS")
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        os.environ["MIN_BLOCK_CHARS"] = str(max(1, int(min_block_chars)))
        from scripts.backfill_blocks_jobs import main as backfill_main

        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = int(backfill_main(["--limit", str(max(1, int(entry_limit)))]))
    except SystemExit as e:
        rc = int(e.code) if isinstance(e.code, int) else 1
    except Exception as e:
        logger.exception("enqueue_latest failed: %s: %s", type(e).__name__, e)
        rc = 1
        stderr_text = stderr_buf.getvalue()
        if stderr_text:
            stderr_text += "\n"
        stderr_text += f"{type(e).__name__}: {e}"
        stderr_buf = io.StringIO(stderr_text)
    finally:
        if old_env is None:
            os.environ.pop("MIN_BLOCK_CHARS", None)
        else:
            os.environ["MIN_BLOCK_CHARS"] = old_env

    out = stdout_buf.getvalue().strip()
    err = stderr_buf.getvalue().strip()
    if out:
        logger.info("enqueue_latest backfill out=%s", out)
    if err:
        logger.warning("enqueue_latest backfill err=%s", err)
    return {
        "ok": rc == 0,
        "queued": rc == 0,
        "entry_limit": int(entry_limit),
        "job_limit": int(job_limit),
        "stdout": out,
        "stderr": err,
        "backfill_rc": int(rc),
        "base_dir": str(base_dir),
    }
