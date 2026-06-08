from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from core.settings import env_int
from storage.repo_audio import list_recent_audio_entries
from utils.timeutil import local_today_str

router = APIRouter()
MAX_AUDIO_UPLOAD_BYTES = env_int("DIARY_MAX_AUDIO_UPLOAD_MB", 25) * 1024 * 1024


class ReanalyzeAudioRequest(BaseModel):
    id: int
    preferred_provider: str = "deepseek"
    force_reanalyze: bool = False


@router.post("/api/diary/audio/save")
async def save_audio_diary(
    request: Request,
    audio: UploadFile = File(...),
    date: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
):
    from services.audio_ingest_service import save_audio_diary_payload

    ingest_entry = getattr(request.app.state, "ingest_entry", None)
    InputError = getattr(request.app.state, "InputError", Exception)
    return await save_audio_diary_payload(
        request=request,
        audio=audio,
        date_str=(date or local_today_str()),
        note=note,
        max_audio_upload_bytes=MAX_AUDIO_UPLOAD_BYTES,
        ingest_entry=ingest_entry,
        input_error_type=InputError,
    )


@router.get("/api/diary/audio/list")
async def list_audio_diaries(limit: int = Query(default=30, ge=1, le=365)):
    items = list_recent_audio_entries(limit=limit)
    return {"ok": True, "count": len(items), "items": items}


@router.get("/api/diary/audio/profile")
async def get_audio_profile(limit: int = Query(default=30, ge=3, le=365)):
    from services.audio_query_service import get_audio_profile_payload

    return get_audio_profile_payload(limit=int(limit))


@router.get("/api/diary/audio/detail")
async def get_audio_detail(id: int = Query(..., ge=1)):
    from services.audio_query_service import get_audio_detail_payload
    from services.media_service import build_transcript_profile

    payload = get_audio_detail_payload(int(id))
    if not payload:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "audio entry not found"})
    transcript_text = str(((payload.get("transcript") or {}).get("text") or ""))
    transcript_profile = build_transcript_profile(transcript_text)

    return {
        "ok": True,
        "audio_entry": payload.get("audio_entry"),
        "content_link": payload.get("content_link"),
        "transcript": payload.get("transcript"),
        "cloud_profile": payload.get("cloud_profile"),
        "transcript_profile": transcript_profile,
    }


@router.get("/api/diary/audio/file")
async def get_audio_file(
    request: Request,
    id: int = Query(..., ge=1),
    prefer: str = Query(default="raw"),
):
    from services.media_service import build_audio_file_response

    return build_audio_file_response(
        request=request,
        audio_id=int(id),
        prefer=prefer,
    )


@router.post("/api/diary/audio/reanalyze")
async def reanalyze_audio_diary(req: ReanalyzeAudioRequest, request: Request):
    from services.audio_ingest_service import reanalyze_audio_diary_payload

    ingest_entry = getattr(request.app.state, "ingest_entry", None)
    InputError = getattr(request.app.state, "InputError", Exception)
    return await reanalyze_audio_diary_payload(
        request=request,
        audio_id=int(req.id),
        preferred_provider=req.preferred_provider,
        force_reanalyze=bool(req.force_reanalyze),
        ingest_entry=ingest_entry,
        input_error_type=InputError,
    )
