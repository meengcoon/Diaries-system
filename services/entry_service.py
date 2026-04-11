from __future__ import annotations

from typing import Any, Dict, Optional

from core.settings import env_int
from storage.repo_analysis_runs import list_analysis_runs
from storage.repo_entries import get_entry_analysis_brief
from storage.repo_jobs import (
    get_entry_job_status_summary,
    list_entry_blocks,
)
from storage.db_core import connect


def entry_failure_reasons(entry_id: int, *, limit: int = 4) -> list[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT b.idx, j.attempts, j.last_error
            FROM block_jobs j
            JOIN entry_blocks b ON b.block_id = j.block_id
            WHERE b.entry_id=?
              AND j.status='failed'
              AND COALESCE(j.last_error, '') <> ''
            ORDER BY b.idx ASC, j.updated_at DESC
            LIMIT ?
            """,
            (int(entry_id), int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            msg = str(row["last_error"] or "").strip()
            if not msg:
                continue
            out.append(
                {
                    "block_idx": int(row["idx"] or 0),
                    "attempts": int(row["attempts"] or 0),
                    "message": msg[:400],
                }
            )
        return out
    finally:
        conn.close()


def summarize_entry_analysis_pipeline(entry_id: int) -> Dict[str, Any]:
    blocks = list_entry_blocks(int(entry_id))
    if not blocks:
        return {
            "has_staged_runs": False,
            "block_count": 0,
            "stage_order": ["evidence", "deep", "normalize", "normalize_repair", "final"],
            "stage_totals": {},
            "blocks": [],
        }

    stage_order = ["evidence", "deep", "normalize", "normalize_repair", "final"]
    stage_totals: Dict[str, Dict[str, int]] = {}
    block_items: list[Dict[str, Any]] = []
    has_runs = False

    for block in blocks:
        block_id = int(block.get("block_id") or 0)
        runs = list_analysis_runs(target_type="block", target_id=block_id, limit=24)
        latest_by_stage: Dict[str, Dict[str, Any]] = {}
        for run in runs:
            stage = str(run.get("stage") or "")
            if not stage or stage in latest_by_stage:
                continue
            latest_by_stage[stage] = run
        if latest_by_stage:
            has_runs = True

        stages: list[Dict[str, Any]] = []
        seen_stage_names: set[str] = set()
        for stage_name in stage_order:
            run = latest_by_stage.get(stage_name)
            status = str((run or {}).get("status") or "missing")
            seen_stage_names.add(stage_name)
            stats = stage_totals.setdefault(stage_name, {"ok": 0, "failed": 0, "rejected": 0, "missing": 0})
            stats[status if status in stats else "missing"] += 1
            stages.append(
                {
                    "stage": stage_name,
                    "status": status,
                    "backend": str((run or {}).get("backend") or ""),
                    "provider": str((run or {}).get("provider") or ""),
                    "model": str((run or {}).get("model") or ""),
                    "created_at": str((run or {}).get("created_at") or ""),
                    "error": str((run or {}).get("error") or ""),
                    "ms": (run or {}).get("ms"),
                }
            )

        extra_stage_names = [name for name in latest_by_stage.keys() if name not in seen_stage_names]
        for stage_name in sorted(extra_stage_names):
            run = latest_by_stage[stage_name]
            status = str(run.get("status") or "missing")
            stats = stage_totals.setdefault(stage_name, {"ok": 0, "failed": 0, "rejected": 0, "missing": 0})
            stats[status if status in stats else "missing"] += 1
            stages.append(
                {
                    "stage": stage_name,
                    "status": status,
                    "backend": str(run.get("backend") or ""),
                    "provider": str(run.get("provider") or ""),
                    "model": str(run.get("model") or ""),
                    "created_at": str(run.get("created_at") or ""),
                    "error": str(run.get("error") or ""),
                    "ms": run.get("ms"),
                }
            )

        final_stage = next((item for item in stages if item["stage"] == "final"), None)
        block_items.append(
            {
                "block_id": block_id,
                "idx": int(block.get("idx") or 0),
                "title": str(block.get("title") or ""),
                "raw_preview": str(block.get("raw_text") or "").strip()[:120],
                "final_status": str((final_stage or {}).get("status") or "missing"),
                "stages": stages,
            }
        )

    return {
        "has_staged_runs": has_runs,
        "block_count": len(blocks),
        "stage_order": stage_order,
        "stage_totals": stage_totals,
        "blocks": block_items,
    }


def get_entry_detail_payload(entry_id: int) -> Optional[Dict[str, Any]]:
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT id, created_at, source, raw_text
            FROM entries
            WHERE id=?
            LIMIT 1
            """,
            (int(entry_id),),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    created_at = str(row["created_at"] or "")
    date = created_at[:10] if len(created_at) >= 10 else ""
    analysis = get_entry_analysis_brief(int(entry_id)) or {}
    job_stats = get_entry_job_status_summary(int(entry_id), max_attempts=env_int("DIARY_ANALYZE_MAX_ATTEMPTS", 8))
    analysis_ready = bool(analysis)
    failure_reasons = entry_failure_reasons(int(entry_id))

    if analysis_ready:
        analysis_status = "done"
    elif int(job_stats.get("running", 0) or 0) > 0:
        analysis_status = "running"
    elif int(job_stats.get("pending", 0) or 0) > 0:
        analysis_status = "pending"
    elif int(job_stats.get("failed_retriable", 0) or 0) > 0 or int(job_stats.get("failed_exhausted", 0) or 0) > 0:
        analysis_status = "failed"
    else:
        analysis_status = "idle"

    return {
        "ok": True,
        "entry_id": int(row["id"]),
        "date": date,
        "created_at": created_at,
        "source": str(row["source"] or ""),
        "text": str(row["raw_text"] or ""),
        "analysis_ready": analysis_ready,
        "analysis_status": analysis_status,
        "analysis": analysis,
        "job_stats": job_stats,
        "failure_reasons": failure_reasons,
        "analysis_pipeline": summarize_entry_analysis_pipeline(int(entry_id)),
    }
