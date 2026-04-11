from __future__ import annotations

import json
from typing import Any, Dict, Optional

from storage.repo_audio import (
    get_audio_content_link,
    get_audio_entry,
    list_recent_audio_analyses,
)
from storage.db_core import connect
from pipeline.audio_features import build_voice_profile


def get_audio_detail_payload(audio_id: int) -> Optional[Dict[str, Any]]:
    item = get_audio_entry(int(audio_id))
    if not item:
        return None

    link = get_audio_content_link(int(audio_id))
    transcript_text = None
    transcript_entry_id = None
    transcript_created_at = None
    entry_analysis_obj: Dict[str, Any] = {}
    block_job_stats: Dict[str, int] = {"pending": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 0}
    if link and isinstance(link.get("entry_id"), int):
        conn = connect()
        try:
            row = conn.execute(
                """
                SELECT id, created_at, raw_text
                FROM entries
                WHERE id=?
                LIMIT 1
                """,
                (int(link["entry_id"]),),
            ).fetchone()
            arow = conn.execute(
                """
                SELECT analysis_json
                FROM entry_analysis
                WHERE entry_id=?
                LIMIT 1
                """,
                (int(link["entry_id"]),),
            ).fetchone()
            jrows = conn.execute(
                """
                SELECT j.status, COUNT(*) AS n
                FROM block_jobs j
                JOIN entry_blocks b ON b.block_id = j.block_id
                WHERE b.entry_id=?
                GROUP BY j.status
                """,
                (int(link["entry_id"]),),
            ).fetchall()
        finally:
            conn.close()
        if row:
            transcript_entry_id = int(row["id"])
            transcript_created_at = str(row["created_at"] or "")
            transcript_text = str(row["raw_text"] or "")
        if arow and str(arow["analysis_json"] or "").strip():
            try:
                obj = json.loads(str(arow["analysis_json"] or "{}"))
                if isinstance(obj, dict):
                    entry_analysis_obj = obj
            except Exception:
                entry_analysis_obj = {}
        for jr in jrows or []:
            s = str(jr["status"] or "")
            n = int(jr["n"] or 0)
            if s in block_job_stats:
                block_job_stats[s] = n
            block_job_stats["total"] += n

    return {
        "audio_entry": item,
        "content_link": link,
        "transcript": {
            "entry_id": transcript_entry_id,
            "created_at": transcript_created_at,
            "text": transcript_text,
        },
        "cloud_profile": {
            "provider": str((link or {}).get("provider") or ""),
            "status": str((link or {}).get("status") or ""),
            "error": str((link or {}).get("error") or ""),
            "entry_analysis": entry_analysis_obj,
            "job_stats": block_job_stats,
        },
    }


def get_audio_profile_payload(limit: int = 30) -> Dict[str, Any]:
    analyses = list_recent_audio_analyses(limit=limit)
    profile = build_voice_profile(analyses)
    return {"ok": True, "sampled": len(analyses), "profile": profile}
