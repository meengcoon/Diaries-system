from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.settings import env_int, env_str
from fastapi import BackgroundTasks, HTTPException, Request, UploadFile

from pipeline.audio_features import analyze_audio_file
from pipeline.local_stt import transcribe_audio_file_local
from storage.db_core import _utc_now_iso
from storage.repo_audio import (
    get_audio_content_link,
    get_audio_entry,
    insert_audio_entry,
    upsert_audio_content_link,
)
from storage.repo_entries import get_entry
from .analysis_service import normalize_provider, queue_entry_analysis
from .diary_file_service import audio_dir, safe_audio_ext
from .entry_ingest_service import replace_entry_content_atomic

logger = logging.getLogger(__name__)


def build_audio_content_text(*, note: str, transcript: str) -> str:
    text_parts: list[str] = []
    note_text = str(note or "").strip()
    if note_text:
        text_parts.append(f"【语音备注】{note_text}")
    body = str(transcript or "").strip()
    if body:
        text_parts.append(body)
    return "\n".join(text_parts).strip()


async def save_audio_diary_payload(
    *,
    request: Request,
    background_tasks: BackgroundTasks,
    audio: UploadFile,
    date_str: str,
    note: Optional[str],
    max_audio_upload_bytes: int,
    ingest_entry: Any,
    input_error_type: type[Exception],
) -> Dict[str, Any]:
    audio_folder = audio_dir(request, date_str)
    ext = safe_audio_ext(audio.filename or "", audio.content_type or "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_path = audio_folder / f"{stamp}_{uuid.uuid4().hex[:10]}{ext}"

    total = 0
    with open(target_path, "wb") as f:
        while True:
            chunk = await audio.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_audio_upload_bytes:
                f.close()
                target_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "AUDIO_TOO_LARGE",
                        "message": f"audio file too large (> {max_audio_upload_bytes // (1024 * 1024)}MB)",
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
        created_at=_utc_now_iso(),
    )

    analysis_error = str(analysis.get("error") or "").strip()
    analysis_ok = (analysis_error == "")

    content_analysis: Dict[str, Any] = {
        "enabled": True,
        "attempted": False,
        "ok": False,
        "transcript_chars": 0,
        "entry_id": None,
        "queued_blocks": 0,
        "cloud_analyze_queued": False,
        "provider": None,
        "error": None,
    }
    if ingest_entry is None:
        content_analysis["error"] = "ingest_unavailable"
    else:
        content_analysis["attempted"] = True
        try:
            transcript = await asyncio.to_thread(transcribe_audio_file_local, target_path)
            content_text = build_audio_content_text(note=str(note or ""), transcript=transcript)

            ingest_res = await ingest_entry(text=content_text, source="api_audio")
            content_analysis["ok"] = True
            content_analysis["transcript_chars"] = len(transcript)
            content_analysis["entry_id"] = ingest_res.get("entry_id")
            content_analysis["queued_blocks"] = int(ingest_res.get("queued_blocks", 0) or 0)

            if int(content_analysis["queued_blocks"]) > 0:
                base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
                provider = normalize_provider(
                    env_str("AUDIO_CONTENT_PREFERRED_PROVIDER")
                    or env_str("CLOUD_DEFAULT_PROVIDER", "deepseek")
                    or "deepseek"
                )
                content_analysis["provider"] = provider
                queue_entry_analysis(
                    background_tasks,
                    base_dir=base_dir,
                    entry_id=int(content_analysis["entry_id"]),
                    preferred_provider=provider,
                    max_attempts=env_int("AUDIO_CONTENT_ANALYZE_MAX_ATTEMPTS", 8),
                    job_timeout_s=env_int("AUDIO_CONTENT_ANALYZE_JOB_TIMEOUT_S", 180),
                    force_reanalyze=False,
                )
                content_analysis["cloud_analyze_queued"] = True
            upsert_audio_content_link(
                audio_entry_id=int(audio_entry_id),
                entry_id=int(content_analysis["entry_id"]) if content_analysis.get("entry_id") else None,
                status="done",
                provider=str(content_analysis.get("provider") or ""),
                error=None,
            )
        except input_error_type as e:
            content_analysis["error"] = f"ingest_invalid_input: {e}"
            upsert_audio_content_link(
                audio_entry_id=int(audio_entry_id),
                entry_id=None,
                status="failed",
                provider="",
                error=content_analysis["error"],
            )
        except Exception as e:
            logger.exception(f"audio content analysis failed: {type(e).__name__}: {e}")
            content_analysis["error"] = f"{type(e).__name__}: {e}"
            upsert_audio_content_link(
                audio_entry_id=int(audio_entry_id),
                entry_id=None,
                status="failed",
                provider="",
                error=content_analysis["error"],
            )

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
        "content_analysis": content_analysis,
    }


async def reanalyze_audio_diary_payload(
    *,
    request: Request,
    background_tasks: BackgroundTasks,
    audio_id: int,
    preferred_provider: str,
    force_reanalyze: bool,
    ingest_entry: Any,
    input_error_type: type[Exception],
) -> Dict[str, Any]:
    item = get_audio_entry(int(audio_id))
    if not item:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "audio entry not found"})

    file_path = Path(str(item.get("file_path") or "")).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail={"code": "FILE_NOT_FOUND", "message": "audio file missing"})

    if ingest_entry is None:
        raise HTTPException(status_code=503, detail={"code": "INGEST_UNAVAILABLE", "message": "ingest unavailable"})

    existing_link = get_audio_content_link(int(audio_id)) or {}
    existing_entry_id = int(existing_link.get("entry_id") or 0)

    try:
        transcript = await asyncio.to_thread(transcribe_audio_file_local, file_path)
        content_text = build_audio_content_text(note=str(item.get("note") or ""), transcript=transcript)
        if not content_text:
            raise input_error_type("empty text is not allowed")
        if len(content_text) > 8000:
            raise input_error_type(f"text too long: {len(content_text)} chars (max 8000)")

        linked_entry = get_entry(existing_entry_id) if existing_entry_id > 0 else None

        if linked_entry:
            ingest_res = replace_entry_content_atomic(
                entry_id=existing_entry_id,
                raw_text=content_text,
                created_at=str(linked_entry.get("created_at") or _utc_now_iso()),
            )
            ingest_res["entry_id"] = existing_entry_id
        else:
            ingest_res = await ingest_entry(text=content_text, source="api_audio_reanalyze")
    except input_error_type as e:
        upsert_audio_content_link(
            audio_entry_id=int(audio_id),
            entry_id=(existing_entry_id if existing_entry_id > 0 else None),
            status="failed",
            provider=str(preferred_provider or ""),
            error=f"ingest_invalid_input: {e}",
        )
        raise HTTPException(status_code=400, detail={"code": "INVALID_INPUT", "message": str(e)})
    except Exception as e:
        upsert_audio_content_link(
            audio_entry_id=int(audio_id),
            entry_id=(existing_entry_id if existing_entry_id > 0 else None),
            status="failed",
            provider=str(preferred_provider or ""),
            error=f"{type(e).__name__}: {e}",
        )
        raise HTTPException(status_code=502, detail={"code": "REANALYZE_FAILED", "message": f"{type(e).__name__}: {e}"})

    provider = normalize_provider(preferred_provider or "deepseek")
    entry_id = int(ingest_res.get("entry_id") or 0)
    queued_blocks = int(ingest_res.get("queued_blocks", 0) or 0)
    cloud_queued = False
    if entry_id > 0 and queued_blocks > 0:
        base_dir = Path(getattr(request.app.state, "base_dir", Path(__file__).resolve().parent))
        queue_entry_analysis(
            background_tasks,
            base_dir=base_dir,
            entry_id=entry_id,
            preferred_provider=provider,
            max_attempts=env_int("AUDIO_CONTENT_ANALYZE_MAX_ATTEMPTS", 8),
            job_timeout_s=env_int("AUDIO_CONTENT_ANALYZE_JOB_TIMEOUT_S", 180),
            force_reanalyze=bool(force_reanalyze),
        )
        cloud_queued = True
    upsert_audio_content_link(
        audio_entry_id=int(audio_id),
        entry_id=(entry_id if entry_id > 0 else None),
        status="done",
        provider=provider,
        error=None,
    )

    return {
        "ok": True,
        "audio_id": int(audio_id),
        "entry_id": entry_id,
        "queued_blocks": queued_blocks,
        "provider": provider,
        "cloud_analyze_queued": cloud_queued,
        "transcript_chars": len(transcript),
    }
