from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from llm.ollama_client import OllamaClient, OllamaError
from storage import db as db

from block_analyze import (
    BlockAnalyzeResult,
    BlockInputError,
    AnalysisValidationError,
    MAX_BLOCK_CHARS,
    MIN_BLOCK_CHARS,
    PHI_MODEL,
    PHI_NUM_PREDICT,
    PROMPT_VERSION,
    _looks_like_noise_block,
    analyze_block,
    run_staged_block_analysis,
    StageCallResult,
)
from pipeline.analysis_quality import attach_analysis_quality
from pipeline.rollup_entry import persist_entry_rollup
from pipeline.memory_update import update_mem_cards_for_entry
from storage.repo_entries import get_entry_version
from storage.repo_jobs import get_entry_block

try:
    from bot.generation_router import generate as routed_generate
except Exception:
    routed_generate = None  # type: ignore


def _maybe_rollup_entry(entry_id: int, *, max_attempts: int, expected_entry_version: Optional[int] = None) -> dict | None:
    """If all jobs for `entry_id` are terminal, persist the entry rollup."""
    s = db.get_entry_job_status_summary(int(entry_id), max_attempts=int(max_attempts))
    if s.get("total", 0) <= 0:
        return None
    if (s.get("pending", 0) + s.get("running", 0) + s.get("failed_retriable", 0)) != 0:
        return None
    return persist_entry_rollup(int(entry_id), expected_entry_version=expected_entry_version)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mark_job_skipped(job_id: int, err: str) -> None:
    db.mark_block_job_skipped(int(job_id), last_error=err)


def _mark_job_failed(job_id: int, err: str) -> None:
    db.mark_block_job_failed(int(job_id), last_error=err)


def _job_stats() -> dict:
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
    entry_version: Optional[int],
    analysis_hash: Optional[str],
    client: OllamaClient,
) -> dict:
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
            entry_version=entry_version,
            analysis_hash=analysis_hash,
            client=client,
        )
        return {
            "entry_id": int(entry_id),
            "attempted": bool(res.get("attempted", True)),
            "ok": bool(res.get("ok", False)),
            "updated": int(res.get("updated", 0) or 0),
            "changes": int(res.get("changes", 0) or 0),
            "card_ids": res.get("card_ids") or [],
            "error": res.get("error"),
            "prompt_version": res.get("prompt_version"),
            "ms": int(res.get("ms", 0) or 0),
            "skipped_reason": res.get("skipped_reason"),
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
        async def _rollup_and_maybe_update_memory(entry_id: int, *, expected_entry_version: Optional[int]) -> None:
            r = _maybe_rollup_entry(entry_id, max_attempts=max_attempts, expected_entry_version=expected_entry_version)
            if not r:
                return
            if r.get("ignored_stale"):
                rollups.append(r)
                return
            mem = await _maybe_update_memory_for_entry(
                entry_id=int(entry_id),
                rollup_meta=r.get("rollup_meta") or {},
                entry_version=(r.get("entry_version") if isinstance(r.get("entry_version"), int) else None),
                analysis_hash=(str(r.get("analysis_hash") or "") or None),
                client=client,
            )
            r["memory"] = mem
            memory_updates.append(mem)
            rollups.append(r)

        lease_owner = f"analysis_worker:{uuid.uuid4().hex[:12]}"

        for _ in range(int(limit)):
            lease_seconds = int(job_timeout_s) if job_timeout_s and job_timeout_s > 0 else 1800
            job = db.claim_next_block_job(
                retry_failed=bool(retry_failed),
                max_attempts=int(max_attempts),
                lease_seconds=max(lease_seconds, 30),
                lease_owner=lease_owner,
                exclude_job_ids=seen_job_ids,
            )
            if not job:
                break

            job_id = int(job["job_id"])
            if job_id in seen_job_ids:
                db.mark_block_job_failed(job_id, last_error=str(job.get("last_error") or "repeat_claim_same_run"))
                repeat_claims += 1
                break
            seen_job_ids.add(job_id)

            block_id = int(job["block_id"])
            entry_id = int(job["entry_id"])
            entry_version = int(job.get("entry_version") or 0)
            title = job.get("title")
            raw_text = job.get("raw_text") or ""
            result_model = f"local:{PHI_MODEL}" if backend == "local" else f"cloud:{preferred_provider or 'deepseek'}"

            current_entry_version = get_entry_version(int(entry_id))
            if entry_version > 0 and current_entry_version != entry_version:
                _mark_job_skipped(job_id, f"stale_entry_version job={entry_version} current={current_entry_version}")
                processed += 1
                skipped += 1
                continue

            latest_stage_errors: dict[str, str] = {}

            def _top_level_error_from_exception(err: Exception) -> str:
                if isinstance(err, AnalysisValidationError):
                    for stage_name in ("normalize_repair", "normalize"):
                        detail = str(latest_stage_errors.get(stage_name) or "").strip()
                        if detail:
                            return detail
                return f"{type(err).__name__}: {err!r}"

            def _record_stage(
                *,
                stage: str,
                prompt_version: str,
                status: str,
                input_json: str | None,
                output_json: str | None,
                error: str | None,
                ms: int | None,
                model: str | None,
                backend_override: str | None = None,
            ) -> None:
                if status == "failed" and error:
                    latest_stage_errors[str(stage)] = str(error)
                provider = None
                if model and ":" in model:
                    provider = model.split(":", 1)[0]
                backend_to_store = str(backend_override or backend)
                db.insert_analysis_run(
                    target_type="block",
                    target_id=block_id,
                    stage=stage,
                    backend=backend_to_store,
                    provider=provider,
                    model=model,
                    prompt_version=prompt_version,
                    status=status,
                    input_json=input_json,
                    output_json=output_json,
                    error=error,
                    ms=ms,
                )

            try:
                if backend == "cloud":
                    coro = analyze_block_cloud(
                        title=title,
                        raw_text=raw_text,
                        preferred_provider=preferred_provider,
                        stage_recorder=_record_stage,
                    )
                else:
                    coro = analyze_block(title=title, raw_text=raw_text, client=client, stage_recorder=_record_stage)
                res = await asyncio.wait_for(coro, timeout=job_timeout_s) if job_timeout_s > 0 else await coro

                current_entry_version = get_entry_version(int(entry_id))
                current_block = get_entry_block(int(block_id))
                if entry_version > 0 and (current_entry_version != entry_version or not current_block):
                    _mark_job_skipped(job_id, f"stale_after_analysis job={entry_version} current={current_entry_version}")
                    processed += 1
                    skipped += 1
                    continue

                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json=json.dumps(res.analysis, ensure_ascii=False),
                    model=result_model,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=True,
                    error=None,
                )
                db.mark_block_job_ok(job_id)
                processed += 1
                ok += 1

                await _rollup_and_maybe_update_memory(entry_id, expected_entry_version=entry_version or None)

            except BlockInputError as e:
                err = f"{type(e).__name__}: {e}"
                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json="{}",
                    model=result_model,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_skipped(job_id, err)
                processed += 1
                skipped += 1

                await _rollup_and_maybe_update_memory(entry_id, expected_entry_version=entry_version or None)

            except asyncio.CancelledError:
                err = "CancelledError: worker interrupted"
                try:
                    db.upsert_block_analysis(
                        block_id=block_id,
                        analysis_json="{}",
                        model=result_model,
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
                    model=result_model,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_failed(job_id, err)
                processed += 1
                failed += 1

                await _rollup_and_maybe_update_memory(entry_id, expected_entry_version=entry_version or None)

            except Exception as e:
                err = _top_level_error_from_exception(e)
                db.upsert_block_analysis(
                    block_id=block_id,
                    analysis_json="{}",
                    model=result_model,
                    prompt_version=PROMPT_VERSION,
                    created_at=_now(),
                    ok=False,
                    error=err,
                )
                _mark_job_failed(job_id, err)
                processed += 1
                failed += 1

                await _rollup_and_maybe_update_memory(entry_id, expected_entry_version=entry_version or None)

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


async def analyze_block_cloud(
    *,
    title: str | None,
    raw_text: str,
    preferred_provider: str,
    stage_recorder=None,
) -> BlockAnalyzeResult:
    text = (raw_text or "").strip()
    if len(text) < MIN_BLOCK_CHARS:
        raise BlockInputError(f"block too short: {len(text)} chars")
    if len(text) > MAX_BLOCK_CHARS:
        raise BlockInputError(f"block too long: {len(text)} chars (max {MAX_BLOCK_CHARS})")
    if _looks_like_noise_block(text):
        raise BlockInputError("block looks like test/log/noise content")
    if routed_generate is None:
        raise RuntimeError("generation_router unavailable; cannot use cloud backend")

    pp = (preferred_provider or "").strip().lower()

    async def _cloud_call(stage: str, messages: list[dict[str, str]], response_format: Optional[dict[str, Any]], max_tokens: int) -> StageCallResult:
        payload = {
            "intent": "long_write",
            "prompt_version": f"{PROMPT_VERSION}:{stage}",
            "force_cloud": True,
            "fallback_backend": "none",
        }
        if pp in {"deepseek", "qwen"}:
            payload["preferred_provider"] = pp
        res = await asyncio.to_thread(
            routed_generate,
            task="block_analyze",
            payload=payload,
            messages=messages,
            response_format=response_format,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        return StageCallResult(
            output=str(res.content or ""),
            ms=int(res.ms or 0),
            model=f"cloud:{pp or 'deepseek'}",
        )

    async with OllamaClient(timeout_s=0.0) as local_client:
        local_ready: bool | None = None

        async def _local_call(stage: str, messages: list[dict[str, str]], response_format: Optional[dict[str, Any]], max_tokens: int) -> StageCallResult:
            nonlocal local_ready
            if local_ready is None:
                local_ready = await local_client.ensure_server_available()
            if not local_ready:
                raise OllamaError(
                    f"local fallback unavailable: Ollama server is not reachable at {local_client.base_url}"
                )
            content, ms = await local_client.chat_text(
                model=PHI_MODEL,
                messages=messages,
                options={"temperature": 0, "top_p": 0.1, "num_predict": max_tokens},
            )
            return StageCallResult(output=content, ms=ms, model=f"local:{PHI_MODEL}")

        return await run_staged_block_analysis(
            title=title,
            raw_text=raw_text,
            stage_caller=_cloud_call,
            fallback_stage_caller=_local_call,
            stage_recorder=stage_recorder,
        )


async def run_forever(
    *,
    limit: int,
    max_attempts: int,
    retry_failed: bool,
    timeout_s: float,
    job_timeout_s: float,
    stale_seconds: int,
    backend: str,
    preferred_provider: str,
    poll_seconds: float,
) -> int:
    while True:
        unstuck = db.reset_stale_running_block_jobs(stale_seconds=int(stale_seconds))
        stats_before = _job_stats()
        out = await run_once(
            limit=int(limit),
            max_attempts=int(max_attempts),
            retry_failed=bool(retry_failed),
            timeout_s=float(timeout_s),
            job_timeout_s=float(job_timeout_s),
            backend=str(backend),
            preferred_provider=str(preferred_provider),
        )
        out["unstuck"] = unstuck
        out["backend"] = str(backend)
        out["preferred_provider"] = str(preferred_provider)
        out["stats_before"] = stats_before
        out["stats_after"] = _job_stats()
        out["loop"] = True
        print(json.dumps(out, ensure_ascii=False), flush=True)
        if int(out.get("processed", 0) or 0) <= 0:
            await asyncio.sleep(max(1.0, float(poll_seconds)))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--retry-failed", action="store_true")
    p.add_argument("--idle-seconds", type=int, default=600)
    p.add_argument("--force", action="store_true")
    p.add_argument("--stats", action="store_true", help="print queue statistics and exit")
    p.add_argument("--timeout-s", type=float, default=0.0)
    p.add_argument("--job-timeout-s", type=float, default=0.0)
    p.add_argument("--stale-seconds", type=int, default=1800)
    p.add_argument("--backend", choices=["local", "cloud"], default="cloud")
    p.add_argument("--preferred-provider", choices=["deepseek", "qwen"], default="deepseek")
    p.add_argument("--loop", action="store_true", help="keep polling the queue as a long-running worker")
    p.add_argument("--poll-seconds", type=float, default=5.0)

    args = p.parse_args(argv)

    db.init_db()

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
        if args.loop:
            return int(
                asyncio.run(
                    run_forever(
                        limit=int(args.limit),
                        max_attempts=int(args.max_attempts),
                        retry_failed=bool(args.retry_failed),
                        timeout_s=float(args.timeout_s),
                        job_timeout_s=float(args.job_timeout_s),
                        stale_seconds=int(args.stale_seconds),
                        backend=str(args.backend),
                        preferred_provider=str(args.preferred_provider),
                        poll_seconds=float(args.poll_seconds),
                    )
                )
                or 0
            )
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
        out = {"processed": 0, "ok": 0, "failed": 0, "skipped": 0, "cancelled": True}

    out["unstuck"] = unstuck
    out["backend"] = str(args.backend)
    out["preferred_provider"] = str(args.preferred_provider)
    out["stats_before"] = stats_before
    out["stats_after"] = _job_stats()

    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0
