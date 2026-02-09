#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Ensure project root is importable regardless of cwd/PYTHONPATH.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import argparse
import asyncio
import json
import platform
import subprocess
from datetime import datetime, timezone
from typing import Any, Optional

from llm.ollama_client import OllamaClient, OllamaError
from storage import db as db

from block_analyze import (
    BlockAnalyzeResult,
    BlockInputError,
    MAX_BLOCK_CHARS,
    MIN_BLOCK_CHARS,
    PHI_MODEL,
    PHI_NUM_PREDICT,
    PROMPT_VERSION,
    _build_fix_messages,
    _build_messages,
    _parse_or_raise,
    analyze_block,
)
from pipeline.rollup_entry import persist_entry_rollup
from pipeline.memory_update import update_mem_cards_for_entry

try:
    from bot.generation_router import generate as routed_generate
except Exception:
    routed_generate = None  # type: ignore


def _maybe_rollup_entry(entry_id: int, *, max_attempts: int) -> dict | None:
    """If all jobs for `entry_id` are terminal, persist the entry rollup.

    Terminal definition for rollup:
      - no pending
      - no running
      - no failed_retriable (failed with attempts < max_attempts)

    We treat failed_exhausted (attempts >= max_attempts) as terminal so the entry
    still becomes searchable even if a block never succeeded.
    """
    s = db.get_entry_job_status_summary(int(entry_id), max_attempts=int(max_attempts))
    if s.get("total", 0) <= 0:
        return None
    if (s.get("pending", 0) + s.get("running", 0) + s.get("failed_retriable", 0)) != 0:
        return None
    # All terminal: done/skipped/failed_exhausted only
    return persist_entry_rollup(int(entry_id))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mark_job_skipped(job_id: int, err: str) -> None:
    """Mark a job as skipped (non-retryable input issue)."""
    db.mark_block_job_skipped(int(job_id), last_error=err)


def _mark_job_failed(job_id: int, err: str) -> None:
    """Mark a job as failed (retriable)."""
    db.mark_block_job_failed(int(job_id), last_error=err)


def _job_stats() -> dict:
    """Return queue counts by status.

    Uses `count_block_jobs_by_status` to keep DB coupling minimal.
    """
    statuses = ["pending", "running", "done", "failed", "skipped"]
    out = {s: int(db.count_block_jobs_by_status(s)) for s in statuses}
    out["total"] = sum(out.values())
    return out


def _has_any_signal_value(signals: Any) -> bool:
    if not isinstance(signals, dict):
        return False
    for v in signals.values():
        if isinstance(v, (int, float)):
            return True
    return False


def _should_update_memory(analysis_obj: Optional[dict]) -> bool:
    """Gate memory writes to entries that contain meaningful rolled-up content."""
    if not isinstance(analysis_obj, dict):
        return False

    topics = analysis_obj.get("topics") or []
    facts = analysis_obj.get("facts") or []
    todos = analysis_obj.get("todos") or []
    summary = str(analysis_obj.get("summary_1_3") or "").strip()
    signals = analysis_obj.get("signals")

    if isinstance(topics, list) and len(topics) > 0:
        return True
    if isinstance(facts, list) and len(facts) > 0:
        return True
    if isinstance(todos, list) and len(todos) > 0:
        return True
    if summary and summary.lower() != "summary not provided":
        return True
    if _has_any_signal_value(signals):
        return True
    return False


async def _maybe_update_memory_for_entry(
    *,
    entry_id: int,
    rollup_meta: dict,
    client: OllamaClient,
) -> dict:
    """Update mem_cards after rollup when content is meaningful."""
    blocks_ok = int((rollup_meta or {}).get("blocks_ok", 0) or 0)
    if blocks_ok <= 0:
        return {"entry_id": int(entry_id), "attempted": False, "skipped_reason": "no_ok_blocks"}

    analysis_obj = db.get_entry_analysis_brief(int(entry_id)) or {}
    if not _should_update_memory(analysis_obj):
        return {"entry_id": int(entry_id), "attempted": False, "skipped_reason": "not_meaningful"}

    try:
        res = await update_mem_cards_for_entry(
            entry_id=int(entry_id),
            entry_analysis=analysis_obj,
            client=client,
        )
        return {
            "entry_id": int(entry_id),
            "attempted": True,
            "ok": bool(res.get("ok", False)),
            "updated": int(res.get("updated", 0) or 0),
            "changes": int(res.get("changes", 0) or 0),
            "card_ids": res.get("card_ids") or [],
            "error": res.get("error"),
            "prompt_version": res.get("prompt_version"),
            "ms": int(res.get("ms", 0) or 0),
        }
    except Exception as e:
        return {
            "entry_id": int(entry_id),
            "attempted": True,
            "ok": False,
            "updated": 0,
            "changes": 0,
            "card_ids": [],
            "error": f"memory_update_failed: {type(e).__name__}: {e}",
        }


def get_idle_seconds() -> float | None:
    """Return current HID idle seconds on macOS, otherwise None."""
    if platform.system() != "Darwin":
        return None
    try:
        cmd = ["bash", "-lc", "ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}'"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        if not out:
            return None
        return float(out) / 1e9
    except Exception:
        return None


async def run_once(
    *,
    limit: int,
    max_attempts: int,
    retry_failed: bool,
    timeout_s: float,
    job_timeout_s: float,
    backend: str,
    preferred_provider: str,
) -> dict:
    processed = ok = failed = skipped = 0
    rollups: list[dict] = []
    memory_updates: list[dict] = []
    seen_job_ids: set[int] = set()
    repeat_claims = 0

    async with OllamaClient(timeout_s=timeout_s) as client:
        async def _rollup_and_maybe_update_memory(entry_id: int) -> None:
            r = _maybe_rollup_entry(entry_id, max_attempts=max_attempts)
            if not r:
                return
            mem = await _maybe_update_memory_for_entry(
                entry_id=int(entry_id),
                rollup_meta=r.get("rollup_meta") or {},
                client=client,
            )
            r["memory"] = mem
            memory_updates.append(mem)
            rollups.append(r)

        for _ in range(int(limit)):
            job = db.claim_next_block_job(retry_failed=bool(retry_failed), max_attempts=int(max_attempts))
            if not job:
                break

            job_id = int(job["job_id"])
            if job_id in seen_job_ids:
                # Prevent tight-loop retries of the same failed jobs in one run.
                # This job has already been claimed in this run; return it to a retryable state
                # instead of leaving it stuck as `running`.
                db.mark_block_job_failed(job_id, last_error="deferred_same_run")
                repeat_claims += 1
                break
            seen_job_ids.add(job_id)

            block_id = int(job["block_id"])
            entry_id = int(job["entry_id"])
            title = job.get("title")
            raw_text = job.get("raw_text") or ""

            try:
                if backend == "cloud":
                    coro = analyze_block_cloud(
                        title=title,
                        raw_text=raw_text,
                        preferred_provider=preferred_provider,
                    )
                else:
                    coro = analyze_block(title=title, raw_text=raw_text, client=client)
                res = await asyncio.wait_for(coro, timeout=job_timeout_s) if job_timeout_s > 0 else await coro

                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json=json.dumps(res.analysis, ensure_ascii=False),
                    model=PHI_MODEL,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=True,
                    error=None,
                )
                db.mark_block_job_ok(job_id)
                processed += 1
                ok += 1

                await _rollup_and_maybe_update_memory(entry_id)

            except BlockInputError as e:
                # Non-retryable input issue (e.g., separators like '---' or too-short blocks).
                err = f"{type(e).__name__}: {e}"
                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json="{}",
                    model=PHI_MODEL,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_skipped(job_id, err)
                processed += 1
                skipped += 1

                await _rollup_and_maybe_update_memory(entry_id)

            except asyncio.CancelledError:
                # Best-effort: do not leave the job in `running` when interrupted interactively.
                err = "CancelledError: worker interrupted"
                try:
                    db.upsert_block_analysis(
                        block_id=block_id,
                        analysis_json="{}",
                        model=PHI_MODEL,
                        prompt_version=PROMPT_VERSION,
                        created_at=_now(),
                        ok=False,
                        error=err,
                    )
                    _mark_job_failed(job_id, err)
                finally:
                    raise

            except OllamaError as e:
                err = f"{type(e).__name__}: {e}"
                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json="{}",
                    model=PHI_MODEL,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_failed(job_id, err)
                processed += 1
                failed += 1

                await _rollup_and_maybe_update_memory(entry_id)

            except Exception as e:
                err = f"{type(e).__name__}: {e!r}"
                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json="{}",
                    model=PHI_MODEL,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_failed(job_id, err)
                processed += 1
                failed += 1

                await _rollup_and_maybe_update_memory(entry_id)

    return {
        "processed": processed,
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
        "rollups": rollups,
        "memory_updates": memory_updates,
        "memory_updates_attempted": sum(1 for x in memory_updates if x.get("attempted")),
        "memory_updates_ok": sum(1 for x in memory_updates if x.get("attempted") and x.get("ok")),
        "memory_updates_skipped": sum(1 for x in memory_updates if not x.get("attempted")),
        "unique_jobs": len(seen_job_ids),
        "repeat_claims": repeat_claims,
    }


async def analyze_block_cloud(*, title: str | None, raw_text: str, preferred_provider: str) -> BlockAnalyzeResult:
    text = (raw_text or "").strip()
    if len(text) < MIN_BLOCK_CHARS:
        raise BlockInputError(f"block too short: {len(text)} chars")
    if len(text) > MAX_BLOCK_CHARS:
        raise BlockInputError(f"block too long: {len(text)} chars (max {MAX_BLOCK_CHARS})")
    if routed_generate is None:
        raise RuntimeError("generation_router unavailable; cannot use cloud backend")

    messages = _build_messages(title=title, raw_text=text)
    payload = {
        "intent": "long_write",
        "prompt_version": PROMPT_VERSION,
        "force_cloud": True,
        "fallback_backend": "none",
    }
    pp = (preferred_provider or "").strip().lower()
    if pp in {"deepseek", "qwen"}:
        payload["preferred_provider"] = pp

    res = await asyncio.to_thread(
        routed_generate,
        task="block_analyze",
        payload=payload,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=PHI_NUM_PREDICT,
    )
    raw_output = str(res.content or "")
    try:
        obj = _parse_or_raise(raw_output)
        return BlockAnalyzeResult(analysis=obj, ms=int(res.ms or 0), raw_output=raw_output)
    except Exception:
        # Keep parity with local analyzer: one explicit repair pass.
        fix_messages = _build_fix_messages(raw_output)
        try:
            res2 = await asyncio.to_thread(
                routed_generate,
                task="block_analyze",
                payload=payload,
                messages=fix_messages,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=PHI_NUM_PREDICT,
            )
            raw2 = str(res2.content or "")
            obj2 = _parse_or_raise(raw2)
            return BlockAnalyzeResult(analysis=obj2, ms=int((res.ms or 0) + (res2.ms or 0)), raw_output=raw2)
        except Exception:
            # Final safety net: deterministic minimal analysis to avoid permanent failed loops.
            fallback = _fallback_analysis_from_text(text)
            return BlockAnalyzeResult(analysis=fallback, ms=int(res.ms or 0), raw_output=raw_output)


def _fallback_analysis_from_text(text: str) -> dict:
    s = (text or "").strip()
    summary = s[:180].strip()
    if not summary:
        summary = "Summary not provided"
    return {
        "summary_1_3": summary,
        "signals": {"mood": None, "stress": None, "sleep": None, "exercise": None, "social": None, "work": None},
        "facts": [summary] if summary and summary != "Summary not provided" else [],
        "todos": [],
        "topics": [],
        "evidence_spans": [],
        "reflection_depth": None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--idle-seconds", type=int, default=600)
    p.add_argument("--force", action="store_true")
    p.add_argument("--stats", action="store_true", help="print queue statistics and exit")

    # timeout_s <= 0 disables read-timeout (wait indefinitely for Ollama response).
    p.add_argument("--timeout-s", type=float, default=0.0)
    # Optional safety guard: abort a single block if it stalls forever.
    p.add_argument("--job-timeout-s", type=float, default=0.0)

    # Stuck job strategy: reset `running` jobs whose updated_at is older than stale_seconds.
    p.add_argument("--stale-seconds", type=int, default=1800)
    p.add_argument("--backend", choices=["local", "cloud"], default="local")
    p.add_argument("--preferred-provider", choices=["deepseek", "qwen"], default="deepseek")

    args = p.parse_args(argv)

    db.init_db()

    # Always run unstuck FIRST, even if we later skip due to idle gating.
    unstuck = db.reset_stale_running_block_jobs(stale_seconds=int(args.stale_seconds))
    stats_before = _job_stats()

    if args.stats:
        print(json.dumps({"stats": stats_before, "unstuck": unstuck}, ensure_ascii=False), flush=True)
        return 0

    if not args.force and args.idle_seconds > 0:
        idle = get_idle_seconds()
        if idle is None:
            print(
                json.dumps(
                    {"skipped": True, "reason": "idle_check_unavailable", "unstuck": unstuck, "stats": stats_before},
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 0
        if idle < args.idle_seconds:
            print(
                json.dumps(
                    {
                        "skipped": True,
                        "reason": "not_idle",
                        "idle_seconds": int(idle),
                        "unstuck": unstuck,
                        "stats": stats_before,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return 0

    try:
        out = asyncio.run(
            run_once(
                limit=int(args.limit),
                max_attempts=int(args.max_attempts),
                retry_failed=bool(args.retry_failed),
                timeout_s=float(args.timeout_s),
                job_timeout_s=float(args.job_timeout_s),
                backend=str(args.backend),
                preferred_provider=str(args.preferred_provider),
            )
        )
    except KeyboardInterrupt:
        # If Ctrl+C happens outside the coroutine boundary, still emit useful JSON.
        out = {"processed": 0, "ok": 0, "failed": 0, "skipped": 0, "cancelled": True}

    out["unstuck"] = unstuck
    out["backend"] = str(args.backend)
    out["preferred_provider"] = str(args.preferred_provider)
    out["stats_before"] = stats_before
    out["stats_after"] = _job_stats()

    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
