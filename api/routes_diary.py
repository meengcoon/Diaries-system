from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from core.settings import env_int, env_str
from storage.db_core import connect
from storage.repo_entries import (
    delete_entry,
    get_entry,
    list_entries_by_date,
    list_recent_entries_overview,
)
from services.analysis_service import (
    analysis_primary_backend,
    normalize_provider,
    queue_entry_analysis,
    queue_latest_analysis,
)
from services.diary_file_service import (
    append_daily_backup_entry,
    date_from_created_at,
    diaries_dir,
    rewrite_daily_backup_from_db,
    safe_diary_path,
)
from services.entry_ingest_service import replace_entry_content_atomic
from services.entry_service import get_entry_detail_payload
from utils.timeutil import utc_now_iso, local_today_str

logger = logging.getLogger(__name__)

router = APIRouter()


class SaveDiaryRequest(BaseModel):
    text: str
    date: Optional[str] = None


class UpdateDiaryRequest(BaseModel):
    id: int
    text: str


class DeleteDiaryRequest(BaseModel):
    id: int


class ReanalyzeDiaryRequest(BaseModel):
    id: int
    preferred_provider: str = "deepseek"
    force_reanalyze: bool = True
    max_attempts: Optional[int] = None
    job_timeout_s: Optional[int] = None


class AnalyzeLatestRequest(BaseModel):
    entry_limit: int = 60
    job_limit: int = 300
    preferred_provider: str = "deepseek"
    min_block_chars: int = 20
    max_attempts: int = 8
    job_timeout_s: int = 180


@router.get("/api/diary/list")
async def list_diaries(request: Request, limit: int = Query(default=30, ge=1, le=365)):
    rows = list_recent_entries_overview(
        limit=int(limit),
        max_attempts=env_int("DIARY_ANALYZE_MAX_ATTEMPTS", 8),
    )
    items = []
    for r in rows:
        created_at = str(r.get("created_at") or "")
        text = str(r.get("raw_text") or "")
        preview = " ".join(text.strip().split())[:80]
        items.append(
            {
                "entry_id": int(r.get("id") or 0),
                "date": created_at[:10] if len(created_at) >= 10 else "",
                "created_at": created_at,
                "preview": preview,
                "size_bytes": len(text.encode("utf-8")),
                "analysis_ready": bool(r.get("analysis_ready")),
                "analysis_status": str(r.get("analysis_status") or "idle"),
                "analysis_summary": str(r.get("analysis_summary") or ""),
                "analysis_error": str(r.get("analysis_error") or ""),
            }
        )

    return {"ok": True, "count": len(items), "items": items}


@router.get("/api/diary/read")
async def read_diary(request: Request, date: str = Query(...)):
    diaries_path = diaries_dir(request)
    file_path = safe_diary_path(diaries_path, date)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"diary not found: {date}"})

    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return {"ok": True, "date": date, "file": str(file_path), "text": text}


@router.get("/api/diary/entry")
async def read_diary_entry(id: int = Query(..., ge=1)):
    detail = get_entry_detail_payload(int(id))
    if not detail:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"entry not found: {id}"})
    return detail


@router.put("/api/diary/entry")
async def update_diary_entry(req: UpdateDiaryRequest, request: Request):
    entry = get_entry(int(req.id))
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"entry not found: {req.id}"})

    text = str(req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": "empty text is not allowed"})
    if len(text) > 8000:
        raise HTTPException(status_code=413, detail={"code": "INVALID_INPUT", "message": f"text too long: {len(text)} chars (max 8000)"})

    rebuild = replace_entry_content_atomic(
        entry_id=int(req.id),
        raw_text=text,
        created_at=str(entry.get("created_at") or utc_now_iso()),
    )
    date_str = date_from_created_at(str(entry.get("created_at") or ""))
    file_path: Optional[Path] = None
    backup_warning = ""
    try:
        file_path = rewrite_daily_backup_from_db(request=request, date_str=date_str)
    except Exception as e:
        backup_warning = f"daily backup rewrite failed: {type(e).__name__}: {e}"
        logger.warning(backup_warning)

    provider = normalize_provider(env_str("DIARY_SAVE_PREFERRED_PROVIDER") or env_str("CLOUD_DEFAULT_PROVIDER", "deepseek") or "deepseek")
    max_attempts = env_int("DIARY_ANALYZE_MAX_ATTEMPTS", 8)
    job_timeout_s = env_int("DIARY_ANALYZE_JOB_TIMEOUT_S", 180)
    queue_entry_analysis(
        base_dir=Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent)),
        entry_id=int(req.id),
        preferred_provider=provider,
        max_attempts=max_attempts,
        job_timeout_s=job_timeout_s,
        force_reanalyze=True,
    )
    detail = get_entry_detail_payload(int(req.id)) or {}
    return {
        "ok": True,
        "entry_id": int(req.id),
        "file": str(file_path) if file_path else "",
        "backup_warning": backup_warning,
        "queued_blocks": int(rebuild.get("queued_blocks", 0) or 0),
        "block_ids": rebuild.get("block_ids") or [],
        "analysis_ok": bool(detail.get("analysis_ready")),
        "analysis_status": str(detail.get("analysis_status") or "pending"),
        "analysis_backend": analysis_primary_backend(),
        "analysis_queued": True,
        "entry_detail": detail,
        "failure_reasons": detail.get("failure_reasons") or [],
    }


@router.delete("/api/diary/entry")
async def delete_diary_entry(request: Request, id: int = Query(..., ge=1)):
    entry = get_entry(int(id))
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"entry not found: {id}"})
    date_str = date_from_created_at(str(entry.get("created_at") or ""))
    delete_entry(int(id))
    file_path = rewrite_daily_backup_from_db(request=request, date_str=date_str)
    remaining = list_entries_by_date(date_str)
    return {
        "ok": True,
        "deleted_entry_id": int(id),
        "date": date_str,
        "file": str(file_path),
        "remaining_for_day": len(remaining),
    }


@router.post("/api/diary/entry/reanalyze")
async def reanalyze_diary_entry(req: ReanalyzeDiaryRequest, request: Request):
    entry = get_entry(int(req.id))
    if not entry:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": f"entry not found: {req.id}"})

    provider = normalize_provider(req.preferred_provider or "deepseek")
    queue_entry_analysis(
        base_dir=Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent)),
        entry_id=int(req.id),
        preferred_provider=provider,
        max_attempts=int(req.max_attempts or env_int("DIARY_ANALYZE_MAX_ATTEMPTS", 8)),
        job_timeout_s=int(req.job_timeout_s or env_int("DIARY_ANALYZE_JOB_TIMEOUT_S", 180)),
        force_reanalyze=bool(req.force_reanalyze),
    )
    detail = get_entry_detail_payload(int(req.id)) or {}
    return {
        "ok": True,
        "entry_id": int(req.id),
        "analysis_ok": bool(detail.get("analysis_ready")),
        "analysis_status": str(detail.get("analysis_status") or "pending"),
        "analysis_backend": analysis_primary_backend(),
        "analysis_queued": True,
        "entry_detail": detail,
        "failure_reasons": detail.get("failure_reasons") or [],
        "analysis_rounds": [],
    }


@router.post("/api/diary/analyze_latest")
async def analyze_latest(req: AnalyzeLatestRequest, request: Request):
    base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
    queued = queue_latest_analysis(
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
        "queued": bool(queued.get("queued", False)),
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
async def save_diary(req: SaveDiaryRequest, request: Request):
    """保存日记：写 txt 备份 + 增量写 SQLite，并在后台触发分析。"""
    logger.info(f"保存日记: 长度={len(req.text)}")

    # 1) 先做 ingest，避免输入非法时先写入 txt 造成文件/数据库状态分裂
    date_str = req.date or local_today_str()

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

    # 3) ingest 成功后再写 txt 备份；备份失败不影响主库成功写入
    ts = utc_now_iso()
    file_path: Optional[Path] = None
    backup_warning = ""
    try:
        file_path = append_daily_backup_entry(
            request=request,
            date_str=date_str,
            created_at=ts,
            text=req.text,
        )
    except Exception as e:
        backup_warning = f"daily backup append failed: {type(e).__name__}: {e}"
        logger.warning(backup_warning)

    entry_id = ingest_res.get("entry_id")

    provider = normalize_provider(env_str("DIARY_SAVE_PREFERRED_PROVIDER") or env_str("CLOUD_DEFAULT_PROVIDER", "deepseek") or "deepseek")
    max_attempts = env_int("DIARY_ANALYZE_MAX_ATTEMPTS", 8)
    job_timeout_s = env_int("DIARY_ANALYZE_JOB_TIMEOUT_S", 180)
    base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
    queued_blocks = int(ingest_res.get("queued_blocks", 0) or 0)
    analysis_queued = bool(entry_id) and queued_blocks > 0
    if analysis_queued:
        queue_entry_analysis(
            base_dir=base_dir,
            entry_id=int(entry_id),
            preferred_provider=provider,
            max_attempts=max_attempts,
            job_timeout_s=job_timeout_s,
            force_reanalyze=False,
        )
    detail = get_entry_detail_payload(int(entry_id)) or {}

    return {
        "ok": True,
        "entry_id": entry_id,
        "file": str(file_path) if file_path else "",
        "backup_warning": backup_warning,
        # Step 1: blocks/jobs observability
        "queued_blocks": queued_blocks,
        "block_ids": ingest_res.get("block_ids") or [],
        "enqueue_ms": ingest_res.get("enqueue_ms"),
        # 可观测性：写入/抽取耗时与是否成功
        "analysis_ok": bool(detail.get("analysis_ready")),
        "analysis_status": str(detail.get("analysis_status") or ("pending" if analysis_queued else "idle")),
        "analysis_backend": analysis_primary_backend(),
        "analysis_queued": analysis_queued,
        "analysis_result": detail.get("analysis") or {},
        "entry_detail": detail,
        "failure_reasons": detail.get("failure_reasons") or [],
        "analysis_rounds": [],
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
    }
