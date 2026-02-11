from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Query, Request

from storage.db_core import connect

router = APIRouter()


@router.get("/health")
async def health():
    """Basic health check for smoke tests and deployment probes."""
    return {"ok": True}


@router.get("/api/_bot")
async def bot_info(request: Request):
    bot = getattr(request.app.state, "bot", None)
    cascade_import_err = getattr(request.app.state, "cascade_import_err", None)
    return {
        "bot": getattr(bot, "__class__", type("X", (), {})).__name__ if bot else None,
        "cascade_import_err": cascade_import_err,
        "server_file": str(Path(__file__).resolve()),
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


def _derive_persona(avg_signals: Dict[str, float], top_topics: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    traits: List[str] = []
    strengths: List[str] = []
    weaknesses: List[str] = []

    mood = avg_signals.get("mood")
    stress = avg_signals.get("stress")
    social = avg_signals.get("social")
    work = avg_signals.get("work")
    sleep = avg_signals.get("sleep")
    exercise = avg_signals.get("exercise")

    if social is not None and social >= 6:
        traits.append("社交连接感较强")
        strengths.append("愿意与朋友互动，外部支持网络较好")
    elif social is not None and social <= 4:
        traits.append("偏内向或社交保守")
        weaknesses.append("社交能量不足时容易封闭自己")

    if work is not None and work >= 6:
        traits.append("目标导向明显")
        strengths.append("对工作与任务有执行动力")
    elif work is not None and work <= 4:
        weaknesses.append("工作推进节奏波动较大")

    if stress is not None and stress >= 6:
        traits.append("自我要求偏高")
        weaknesses.append("压力管理需要更主动的节奏控制")
    elif stress is not None and stress <= 4:
        strengths.append("压力水平整体可控")

    if mood is not None and mood >= 6:
        strengths.append("情绪恢复能力较好")
    elif mood is not None and mood <= 4:
        weaknesses.append("负面情绪时段可能拉长")

    if sleep is not None and sleep <= 4:
        weaknesses.append("睡眠质量或规律性偏弱")
    elif sleep is not None and sleep >= 6:
        strengths.append("睡眠习惯相对稳定")

    if exercise is not None and exercise >= 6:
        strengths.append("运动习惯提供了情绪缓冲")
    elif exercise is not None and exercise <= 3:
        weaknesses.append("身体活动偏少，可能影响精力")

    if top_topics:
        head = [str(t.get("topic") or "") for t in top_topics[:3] if str(t.get("topic") or "").strip()]
        if head:
            traits.append(f"近期关注主题：{'、'.join(head)}")

    if not traits:
        traits.append("当前可用样本较少，画像还在形成中")
    if not strengths:
        strengths.append("持续记录有助于挖掘稳定优势")
    if not weaknesses:
        weaknesses.append("暂未观察到明显短板，可继续观察趋势")

    return {"traits": traits, "strengths": strengths, "weaknesses": weaknesses}


@router.get("/api/dashboard/overview")
async def dashboard_overview(request: Request, limit: int = Query(default=90, ge=10, le=365)):
    conn = connect()
    try:
        entries_count = int(conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()["n"])
        latest_row = conn.execute(
            "SELECT id, created_at FROM entries ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        analysis_rows = conn.execute(
            "SELECT analysis_json FROM entry_analysis ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        job_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM block_jobs GROUP BY status"
        ).fetchall()
    finally:
        conn.close()

    base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
    diaries_count = len(list((base_dir / "diaries").glob("*.txt")))

    stats = {"pending": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 0}
    for r in job_rows:
        s = str(r["status"])
        n = int(r["n"])
        if s in stats:
            stats[s] = n
        stats["total"] += n

    signal_sum: Dict[str, float] = {"mood": 0, "stress": 0, "sleep": 0, "exercise": 0, "social": 0, "work": 0}
    signal_cnt: Dict[str, int] = {"mood": 0, "stress": 0, "sleep": 0, "exercise": 0, "social": 0, "work": 0}
    topic_counter: Counter[str] = Counter()

    for r in analysis_rows:
        try:
            obj = json.loads(r["analysis_json"] or "{}")
        except Exception:
            obj = {}
        signals = obj.get("signals") or {}
        if isinstance(signals, dict):
            for k in signal_sum.keys():
                v = signals.get(k)
                if isinstance(v, (int, float)):
                    signal_sum[k] += float(v)
                    signal_cnt[k] += 1

        topics = obj.get("topics") or []
        if isinstance(topics, list):
            for t in topics:
                ts = str(t or "").strip()
                if ts:
                    topic_counter[ts] += 1

    avg_signals: Dict[str, float] = {}
    for k in signal_sum.keys():
        if signal_cnt[k] > 0:
            avg_signals[k] = round(signal_sum[k] / signal_cnt[k], 2)

    top_topics = [{"topic": t, "count": c} for t, c in topic_counter.most_common(8)]
    persona = _derive_persona(avg_signals, top_topics)

    return {
        "ok": True,
        "stats": {
            "diaries_count": diaries_count,
            "entries_count": entries_count,
            "analysis_samples": len(analysis_rows),
            "latest_entry_id": int(latest_row["id"]) if latest_row else None,
            "latest_entry_at": latest_row["created_at"] if latest_row else None,
            "jobs": stats,
        },
        "signals_avg": avg_signals,
        "topics": top_topics,
        "persona": persona,
    }
