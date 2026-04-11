from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException, Request

from storage.repo_entries import list_entries_by_date


def diaries_dir(request: Request) -> Path:
    data_dir = Path(
        getattr(
            request.app.state,
            "data_dir",
            getattr(request.app.state, "base_dir", Path(__file__).resolve().parent),
        )
    )
    path = data_dir / "diaries"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_diary_path(diaries_dir_path: Path, date_str: str) -> Path:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        raise HTTPException(status_code=400, detail={"code": "INVALID_DATE", "message": "date must be YYYY-MM-DD"})
    return diaries_dir_path / f"{date_str}.txt"


def audio_dir(request: Request, date_str: str) -> Path:
    diaries_path = diaries_dir(request)
    safe_diary_path(diaries_path, date_str)
    audio_path = diaries_path / "audio" / date_str
    audio_path.mkdir(parents=True, exist_ok=True)
    return audio_path


def safe_audio_ext(filename: str, content_type: str) -> str:
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


def date_from_created_at(ts: str) -> str:
    ts = str(ts or "")
    return ts[:10] if len(ts) >= 10 else ""


def render_daily_backup_text(rows: list[Dict[str, Any]]) -> str:
    chunks: list[str] = []
    for row in rows:
        created_at = str(row.get("created_at") or "")
        text = str(row.get("raw_text") or "").strip()
        if not text:
            continue
        chunks.append(f"\n\n--- {created_at} ---\n{text}\n")
    return "".join(chunks)


def rewrite_daily_backup_from_db(*, request: Request, date_str: str) -> Path:
    file_path = safe_diary_path(diaries_dir(request), date_str)
    rows = list_entries_by_date(date_str)
    content = render_daily_backup_text(rows)
    if content.strip():
        file_path.write_text(content, encoding="utf-8")
    else:
        file_path.unlink(missing_ok=True)
    return file_path


def append_daily_backup_entry(*, request: Request, date_str: str, created_at: str, text: str) -> Path:
    file_path = safe_diary_path(diaries_dir(request), date_str)
    chunk = f"\n\n--- {created_at} ---\n{str(text or '').strip()}\n"
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(chunk)
    return file_path
