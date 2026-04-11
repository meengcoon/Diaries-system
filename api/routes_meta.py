from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Query, Request

from storage.db import list_recent_entry_summaries
from storage.db_core import connect

router = APIRouter()


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/api/_bot")
async def bot_info(request: Request):
    bot = getattr(request.app.state, "bot", None)
    cascade_import_err = getattr(request.app.state, "cascade_import_err", None)
    models = {}
    if bot is not None:
        if getattr(bot, "phi_model", None):
            models["route_model"] = str(getattr(bot, "phi_model"))
        if getattr(bot, "answer_model", None):
            models["answer_model"] = str(getattr(bot, "answer_model"))
    return {
        "bot": getattr(bot, "__class__", type("X", (), {})).__name__ if bot else None,
        "models": models,
        "cascade_import_err": cascade_import_err,
    }


@router.get("/api/_routes")
async def routes_info(request: Request):
    app = request.app
    return {
        "routes": [
            {
                "path": getattr(r, "path", None),
                "name": getattr(r, "name", None),
                "methods": sorted(list(getattr(r, "methods", []) or [])),
            }
            for r in app.router.routes
        ]
    }


@router.get("/api/dashboard/overview")
async def dashboard_overview(limit: int = Query(default=90, ge=10, le=365)):
    del limit

    recent = list_recent_entry_summaries(24)
    topic_counter: Counter[str] = Counter()
    for row in recent:
        for topic in (row.get("topics") or []):
            t = str(topic or "").strip()
            if t:
                topic_counter[t] += 1

    focus_lines = [topic for topic, _count in topic_counter.most_common(6)]
    if not focus_lines:
        focus_lines = ["最近还没有足够的分析结果。"]

    conn = connect()
    try:
        entries_count = int(conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"])
        latest_row = conn.execute(
            "SELECT id, created_at FROM entries ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        job_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM block_jobs GROUP BY status"
        ).fetchall()
    finally:
        conn.close()

    analysis_jobs = {"pending": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 0}
    for row in job_rows:
        status = str(row["status"] or "")
        count = int(row["n"] or 0)
        if status in analysis_jobs:
            analysis_jobs[status] = count
        analysis_jobs["total"] += count

    latest_entry = {
        "entry_id": int(latest_row["id"]) if latest_row else None,
        "created_at": str(latest_row["created_at"] or "") if latest_row else "",
    }

    return {
        "ok": True,
        "simplified": True,
        "notice": "画像面板已精简，只保留核心概览。",
        "entries_count": entries_count,
        "latest_entry": latest_entry,
        "analysis_jobs": analysis_jobs,
        "focus_lines": focus_lines,
    }
