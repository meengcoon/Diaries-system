from __future__ import annotations

import os
import subprocess
import sys
import logging
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from cloud.sync_client import cloud_sync_enabled, sync_diary_file_to_cloud, sync_diary_file_to_cloud_bg
from storage.db_core import connect
from storage.db import insert_audio_entry, list_recent_audio_analyses, list_recent_audio_entries
from pipeline.audio_features import analyze_audio_file, build_voice_profile
from utils.timeutil import utc_now_iso, local_today_str

logger = logging.getLogger(__name__)

router = APIRouter()
MAX_AUDIO_UPLOAD_BYTES = int(os.getenv("DIARY_MAX_AUDIO_UPLOAD_MB", "25")) * 1024 * 1024


# DiaryEntry 仅用于 legacy bot.entries 的增量追加；如果 diary_bot 未导出该类型，使用同字段的本地 dataclass 兜底。
try:
    from diary_bot import DiaryEntry  # type: ignore
except Exception:

    @dataclass
    class DiaryEntry:  # type: ignore
        date: datetime
        text: str
        path: str


class SaveDiaryRequest(BaseModel):
    text: str
    date: Optional[str] = None


class SyncExistingRequest(BaseModel):
    limit: int = 30
    newest_first: bool = True


class AnalyzeLatestRequest(BaseModel):
    entry_limit: int = 60
    job_limit: int = 300
    preferred_provider: str = "deepseek"
    min_block_chars: int = 20
    max_attempts: int = 8
    job_timeout_s: int = 180


def _diaries_dir(request: Request) -> Path:
    base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
    path = base_dir / "diaries"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_diary_path(diaries_dir: Path, date_str: str) -> Path:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DATE", "message": "date must be YYYY-MM-DD"})
    return diaries_dir / f"{date_str}.txt"


def _audio_dir(request: Request, date_str: str) -> Path:
    diaries_dir = _diaries_dir(request)
    _safe_diary_path(diaries_dir, date_str)  # validate date
    audio_path = diaries_dir / "audio" / date_str
    audio_path.mkdir(parents=True, exist_ok=True)
    return audio_path


def _safe_audio_ext(filename: str, content_type: str) -> str:
    suffix = (Path(filename or "").suffix or "").lower()
    allow = {".webm", ".wav", ".m4a", ".mp3", ".ogg", ".opus", ".aac"}
    if suffix in allow:
        return suffix

    ct = (content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "wav" in ct:
        return ".wav"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "ogg" in ct:
        return ".ogg"
    if "mp4" in ct or "m4a" in ct:
        return ".m4a"
    return ".webm"


@router.get("/api/diary/list")
async def list_diaries(request: Request, limit: int = Query(default=30, ge=1, le=365)):
    diaries_dir = _diaries_dir(request)
    files = sorted(diaries_dir.glob("*.txt"), key=lambda p: p.stem, reverse=True)

    items = []
    for p in files[:limit]:
        stat = p.stat()
        text = p.read_text(encoding="utf-8", errors="ignore")
        preview = ""
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("---"):
                preview = line[:80]
                break
        items.append(
            {
                "date": p.stem,
                "file": str(p),
                "size_bytes": stat.st_size,
                "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "preview": preview,
            }
        )

    return {"ok": True, "count": len(items), "items": items}


@router.get("/api/diary/read")
async def read_diary(request: Request, date: str = Query(...)):
    diaries_dir = _diaries_dir(request)
    file_path = _safe_diary_path(diaries_dir, date)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"diary not found: {date}"})

    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return {"ok": True, "date": date, "file": str(file_path), "text": text}


@router.post("/api/diary/audio/save")
async def save_audio_diary(
    request: Request,
    audio: UploadFile = File(...),
    date: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
):
    date_str = date or local_today_str()
    audio_folder = _audio_dir(request, date_str)

    ext = _safe_audio_ext(audio.filename or "", audio.content_type or "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = audio_folder / f"{stamp}_{uuid.uuid4().hex[:10]}{ext}"

    total = 0
    with open(target_path, "wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_AUDIO_UPLOAD_BYTES:
                f.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "AUDIO_TOO_LARGE",
                        "message": f"audio file too large (> {MAX_AUDIO_UPLOAD_BYTES // (1024 * 1024)}MB)",
                    },
                )
            f.write(chunk)
    await audio.close()

    if total <= 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail={"code": "EMPTY_AUDIO", "message": "empty audio upload"})

    analysis = analyze_audio_file(target_path)
    audio_entry_id = insert_audio_entry(
        diary_date=date_str,
        file_path=str(target_path),
        source_format=str(analysis.get("source_ext") or ext),
        duration_s=float(analysis.get("duration_s")) if isinstance(analysis.get("duration_s"), (int, float)) else None,
        file_size_bytes=total,
        note=(note or "").strip()[:500],
        analysis_json=json.dumps(analysis, ensure_ascii=False),
        created_at=utc_now_iso(),
    )

    profile = build_voice_profile(list_recent_audio_analyses(limit=30))
    analysis_error = str(analysis.get("error") or "").strip()
    analysis_ok = (analysis_error == "")
    return {
        "ok": bool(analysis_ok),
        "uploaded": True,
        "analysis_ok": bool(analysis_ok),
        "analysis_error": (analysis_error or None),
        "audio_entry_id": int(audio_entry_id),
        "date": date_str,
        "file": str(target_path),
        "size_bytes": total,
        "analysis": analysis,
        "voice_profile": profile,
    }


@router.get("/api/diary/audio/list")
async def list_audio_diaries(limit: int = Query(default=30, ge=1, le=365)):
    items = list_recent_audio_entries(limit=limit)
    return {"ok": True, "count": len(items), "items": items}


@router.get("/api/diary/audio/profile")
async def get_audio_profile(limit: int = Query(default=30, ge=3, le=365)):
    analyses = list_recent_audio_analyses(limit=limit)
    profile = build_voice_profile(analyses)
    return {"ok": True, "sampled": len(analyses), "profile": profile}


@router.post("/api/diary/cloud/sync_existing")
async def sync_existing_diaries(req: SyncExistingRequest, request: Request):
    diaries_dir = _diaries_dir(request)
    limit = max(1, min(int(req.limit or 30), 365))

    files = list(diaries_dir.glob("*.txt"))
    files.sort(key=lambda p: p.stem, reverse=bool(req.newest_first))
    files = files[:limit]

    if not cloud_sync_enabled():
        return {"ok": False, "msg": "cloud_sync_disabled", "count": 0, "items": []}

    items = []
    ok_count = 0
    skipped_count = 0
    for p in files:
        res = sync_diary_file_to_cloud(str(p), source="api_sync_existing")
        item = {
            "date": p.stem,
            "file": str(p),
            "ok": bool(res.get("ok")),
            "skipped": bool(res.get("skipped")),
            "synced_bytes": res.get("synced_bytes"),
            "total_bytes": res.get("total_bytes"),
            "error": res.get("error"),
        }
        items.append(item)
        if item["ok"]:
            ok_count += 1
        if item["skipped"]:
            skipped_count += 1

    return {"ok": True, "count": len(items), "ok_count": ok_count, "skipped_count": skipped_count, "items": items}


@router.get("/api/diary/cloud/state")
async def cloud_sync_state(limit: int = Query(default=100, ge=1, le=1000)):
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT file_path, synced_bytes, last_file_size, last_source, last_batch_id,
                   last_status, last_error, updated_at
            FROM cloud_sync_state
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return {"ok": True, "count": len(rows), "items": [dict(r) for r in rows]}
    finally:
        conn.close()


def _run_analyze_latest_bg(
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

    try:
        b = subprocess.run(backfill_cmd, cwd=str(base_dir), env=env, capture_output=True, text=True, check=False)
        logger.info(f"analyze_latest backfill rc={b.returncode} out={b.stdout.strip()} err={b.stderr.strip()}")
        r = subprocess.run(run_cmd, cwd=str(base_dir), env=env, capture_output=True, text=True, check=False)
        logger.info(f"analyze_latest run rc={r.returncode} out={r.stdout.strip()} err={r.stderr.strip()}")
    except Exception as e:
        logger.exception(f"analyze_latest background failed: {type(e).__name__}: {e}")


@router.post("/api/diary/analyze_latest")
async def analyze_latest(req: AnalyzeLatestRequest, request: Request, background_tasks: BackgroundTasks):
    base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
    background_tasks.add_task(
        _run_analyze_latest_bg,
        base_dir=base_dir,
        entry_limit=req.entry_limit,
        job_limit=req.job_limit,
        preferred_provider=req.preferred_provider,
        min_block_chars=req.min_block_chars,
        max_attempts=req.max_attempts,
        job_timeout_s=req.job_timeout_s,
    )
    return {
        "ok": True,
        "queued": True,
        "entry_limit": int(req.entry_limit),
        "job_limit": int(req.job_limit),
        "preferred_provider": req.preferred_provider,
    }


@router.get("/api/diary/analyze_status")
async def analyze_status():
    conn = connect()
    try:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM block_jobs GROUP BY status").fetchall()
        stats = {"pending": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 0}
        for r in rows:
            s = str(r["status"])
            n = int(r["n"])
            if s in stats:
                stats[s] = n
            stats["total"] += n
        return {"ok": True, "stats": stats}
    finally:
        conn.close()


@router.post("/api/diary/save")
async def save_diary(req: SaveDiaryRequest, request: Request, background_tasks: BackgroundTasks):
    """保存日记：写 txt 备份 + 增量写 SQLite（不再在保存时运行 Phi/Qwen）"""
    logger.info(f"保存日记: 长度={len(req.text)}")

    # 1) 先做 ingest，避免输入非法时先写入 txt 造成文件/数据库状态分裂
    date_str = req.date or local_today_str()
    file_path = _safe_diary_path(_diaries_dir(request), date_str)

    # 2) 走 ingest：insert_entry -> split_to_blocks -> entry_blocks -> block_jobs（不跑模型）
    ingest_entry = getattr(request.app.state, "ingest_entry", None)
    InputError = getattr(request.app.state, "InputError", Exception)
    if ingest_entry is None:
        raise RuntimeError("ingest 未就绪：请确认存在 pipeline/ingest.py（ingest_entry）")

    try:
        ingest_res = await ingest_entry(text=req.text, source="api")
    except InputError as e:
        # 空文本 / 超长等可解释错误
        msg = str(e)
        status = 413 if "too long" in msg.lower() else 400
        raise HTTPException(status_code=status, detail={"code": "INVALID_INPUT", "message": msg})

    # 3) ingest 成功后再写 txt 备份
    ts = utc_now_iso()
    new_text = (req.text or "").strip()
    chunk = f"\n\n--- {ts} ---\n{new_text}\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(chunk)

    entry_id = ingest_res.get("entry_id")

    # Legacy bot only: CascadeBot does not maintain `entries`
    bot = getattr(request.app.state, "bot", None)
    if bot is not None and hasattr(bot, "entries"):
        try:
            bot.entries.append(
                DiaryEntry(date=datetime.now(timezone.utc), text=req.text, path=str(file_path))  # type: ignore
            )
            bot.entries.sort(key=lambda e: e.date)  # type: ignore
        except Exception:
            # 如果 bot.entries 不是该结构，至少不要因为增量更新而影响保存
            pass

    if cloud_sync_enabled() and (req.text or "").strip():
        background_tasks.add_task(sync_diary_file_to_cloud_bg, str(file_path), source="api_diary_save")

    return {
        "ok": True,
        "entry_id": entry_id,
        "file": str(file_path),
        # Step 1: blocks/jobs observability
        "queued_blocks": int(ingest_res.get("queued_blocks", 0) or 0),
        "block_ids": ingest_res.get("block_ids") or [],
        "enqueue_ms": ingest_res.get("enqueue_ms"),
        # 可观测性：写入/抽取耗时与是否成功
        "analysis_ok": bool(ingest_res.get("analysis_ok", False)),
        "prompt_version": ingest_res.get("prompt_version"),
        "model": ingest_res.get("model"),
        "insert_ms": ingest_res.get("insert_ms"),
        "extract_ms": ingest_res.get("extract_ms"),
        "error": ingest_res.get("error"),
        # M2: mem_cards update observability
        "memory_ok": bool(ingest_res.get("memory_ok", False)),
        "memory_ms": ingest_res.get("memory_ms"),
        "memory_updated": ingest_res.get("memory_updated"),
        "memory_changes": ingest_res.get("memory_changes"),
        "memory_error": ingest_res.get("memory_error"),
        "memory_card_ids": ingest_res.get("memory_card_ids"),
        # Cloud sync observability
        "cloud_sync_enabled": cloud_sync_enabled(),
        "cloud_sync_queued": bool(cloud_sync_enabled() and (req.text or "").strip()),
    }
