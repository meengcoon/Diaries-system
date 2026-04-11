from __future__ import annotations

import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict

from .analysis_config import analysis_primary_backend
from .analysis_jobs import prioritize_entry_jobs
from .entry_service import get_entry_detail_payload

logger = logging.getLogger(__name__)
BLOCK_ANALYZE_PROC_LOCK = threading.Lock()


def run_python_cli(cmd: list[str], *, cwd: Path, env: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    if not getattr(sys, "frozen", False):
        cmd0 = str(cmd[0] or "")
        if cmd0 in {"python", "python3"} and not shutil.which(cmd0):
            cmd = [sys.executable, *cmd[1:]]
        return subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True, check=False)

    if len(cmd) < 2:
        return subprocess.CompletedProcess(cmd, 2, "", "invalid_embedded_command")

    script_name = Path(cmd[1]).name
    argv = cmd[2:]

    if script_name == "backfill_blocks_jobs.py":
        from scripts.backfill_blocks_jobs import main as entrypoint
    elif script_name == "run_block_jobs.py":
        from scripts.run_block_jobs import main as entrypoint
    else:
        return subprocess.CompletedProcess(cmd, 2, "", f"unsupported_embedded_script: {script_name}")

    old_env = os.environ.copy()
    old_cwd = Path.cwd()
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        os.environ.clear()
        os.environ.update(env)
        os.chdir(str(cwd))
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            rc = int(entrypoint(argv))
        return subprocess.CompletedProcess(cmd, rc, stdout_buf.getvalue(), stderr_buf.getvalue())
    except SystemExit as e:
        code = int(e.code) if isinstance(e.code, int) else 1
        return subprocess.CompletedProcess(cmd, code, stdout_buf.getvalue(), stderr_buf.getvalue())
    except Exception as e:
        stderr_text = stderr_buf.getvalue()
        if stderr_text:
            stderr_text += "\n"
        stderr_text += f"{type(e).__name__}: {e}"
        return subprocess.CompletedProcess(cmd, 1, stdout_buf.getvalue(), stderr_text)
    finally:
        os.chdir(str(old_cwd))
        os.environ.clear()
        os.environ.update(old_env)


def log_subprocess_result(label: str, proc: subprocess.CompletedProcess[str]) -> None:
    rc = int(proc.returncode)
    sig_name = ""
    if rc < 0:
        try:
            sig_name = signal.Signals(-rc).name
        except Exception:
            sig_name = f"SIG{-rc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if sig_name:
        logger.info(f"{label} rc={rc} signal={sig_name} out={out} err={err}")
    else:
        logger.info(f"{label} rc={rc} out={out} err={err}")


def should_fallback_to_local(proc: subprocess.CompletedProcess[str]) -> bool:
    try:
        obj = json.loads((proc.stdout or "").strip() or "{}")
        if not isinstance(obj, dict):
            return False
        failed = int(obj.get("failed", 0) or 0)
        ok = int(obj.get("ok", 0) or 0)
        if failed <= 0 or ok > 0:
            return False
    except Exception:
        return False
    err_text = ((proc.stderr or "") + " " + (proc.stdout or "")).lower()
    markers = (
        "certificate_verify_failed",
        "ssl",
        "urlerror",
        "missing_api_key",
        "timed out",
        "connection",
    )
    return any(m in err_text for m in markers)


def detail_should_fallback_to_local(detail: Dict[str, Any]) -> bool:
    reasons = detail.get("failure_reasons") or []
    markers = (
        "certificate_verify_failed",
        "ssl",
        "urlerror",
        "missing_api_key",
        "timed out",
        "connection",
    )
    for item in reasons:
        msg = str((item or {}).get("message") or "").lower()
        if any(marker in msg for marker in markers):
            return True
    return False


def run_analyze_entry_bg(
    *,
    base_dir: Path,
    entry_id: int,
    preferred_provider: str,
    max_attempts: int,
    job_timeout_s: int,
    force_reanalyze: bool = False,
) -> None:
    py = sys.executable or "python3"
    BLOCK_ANALYZE_PROC_LOCK.acquire()

    try:
        pending_n = prioritize_entry_jobs(
            int(entry_id),
            force_reanalyze=bool(force_reanalyze),
            max_attempts=max(1, int(max_attempts)),
        )
        if pending_n <= 0:
            logger.info(f"analyze_entry entry_id={entry_id}: no pending jobs")
            return

        run_cmd = [
            py,
            str(base_dir / "scripts" / "run_block_jobs.py"),
            "--backend",
            "cloud",
            "--preferred-provider",
            str(preferred_provider or "deepseek"),
            "--force",
            "--retry-failed",
            "--max-attempts",
            str(max(1, int(max_attempts))),
            "--limit",
            str(max(1, int(pending_n))),
            "--job-timeout-s",
            str(max(10, int(job_timeout_s))),
        ]
        run_local_cmd = [
            py,
            str(base_dir / "scripts" / "run_block_jobs.py"),
            "--backend",
            "local",
            "--force",
            "--retry-failed",
            "--max-attempts",
            str(max(1, int(max_attempts))),
            "--limit",
            str(max(1, int(pending_n))),
            "--job-timeout-s",
            str(max(10, int(job_timeout_s))),
        ]
        env = dict(os.environ)
        if analysis_primary_backend() == "local":
            rl = run_python_cli(run_local_cmd, cwd=base_dir, env=env)
            log_subprocess_result(
                f"analyze_entry run_local entry_id={entry_id} pending={pending_n}",
                rl,
            )
        else:
            r = run_python_cli(run_cmd, cwd=base_dir, env=env)
            log_subprocess_result(
                f"analyze_entry run entry_id={entry_id} provider={preferred_provider} pending={pending_n}",
                r,
            )
            detail_after = get_entry_detail_payload(int(entry_id)) or {}
            if should_fallback_to_local(r) or detail_should_fallback_to_local(detail_after):
                rl = run_python_cli(run_local_cmd, cwd=base_dir, env=env)
                log_subprocess_result(
                    f"analyze_entry fallback_local entry_id={entry_id} pending={pending_n}",
                    rl,
                )
    except Exception as e:
        logger.exception(f"analyze_entry background failed entry_id={entry_id}: {type(e).__name__}: {e}")
    finally:
        BLOCK_ANALYZE_PROC_LOCK.release()


def run_analyze_latest_bg(
    *,
    base_dir: Path,
    entry_limit: int,
    job_limit: int,
    preferred_provider: str,
    min_block_chars: int,
    max_attempts: int,
    job_timeout_s: int,
) -> None:
    env = dict(os.environ)
    env["MIN_BLOCK_CHARS"] = str(max(1, int(min_block_chars)))

    py = sys.executable or "python3"
    backfill_cmd = [
        py,
        str(base_dir / "scripts" / "backfill_blocks_jobs.py"),
        "--limit",
        str(max(1, int(entry_limit))),
    ]
    run_cmd = [
        py,
        str(base_dir / "scripts" / "run_block_jobs.py"),
        "--backend",
        "cloud",
        "--preferred-provider",
        str(preferred_provider or "deepseek"),
        "--force",
        "--retry-failed",
        "--max-attempts",
        str(max(1, int(max_attempts))),
        "--limit",
        str(max(1, int(job_limit))),
        "--job-timeout-s",
        str(max(10, int(job_timeout_s))),
    ]
    run_local_cmd = [
        py,
        str(base_dir / "scripts" / "run_block_jobs.py"),
        "--backend",
        "local",
        "--force",
        "--retry-failed",
        "--max-attempts",
        str(max(1, int(max_attempts))),
        "--limit",
        str(max(1, int(job_limit))),
        "--job-timeout-s",
        str(max(10, int(job_timeout_s))),
    ]

    BLOCK_ANALYZE_PROC_LOCK.acquire()

    try:
        b = run_python_cli(backfill_cmd, cwd=base_dir, env=env)
        log_subprocess_result("analyze_latest backfill", b)
        if analysis_primary_backend() == "local":
            rl = run_python_cli(run_local_cmd, cwd=base_dir, env=env)
            log_subprocess_result("analyze_latest run_local", rl)
        else:
            r = run_python_cli(run_cmd, cwd=base_dir, env=env)
            log_subprocess_result("analyze_latest run", r)
            if should_fallback_to_local(r):
                rl = run_python_cli(run_local_cmd, cwd=base_dir, env=env)
                log_subprocess_result("analyze_latest fallback_local", rl)
    except Exception as e:
        logger.exception(f"analyze_latest background failed: {type(e).__name__}: {e}")
    finally:
        BLOCK_ANALYZE_PROC_LOCK.release()
