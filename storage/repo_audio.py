from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _safe_json_loads, _utc_now_iso


def insert_audio_entry(
    *,
    diary_date: str,
    file_path: str,
    source_format: str,
    duration_s: Optional[float],
    file_size_bytes: int,
    note: Optional[str],
    analysis_json: str,
    created_at: Optional[str] = None,
) -> int:
    created_at = created_at or _utc_now_iso()
    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO audio_entries(
                created_at, diary_date, file_path, source_format, duration_s, file_size_bytes, note, analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                diary_date,
                file_path,
                source_format or "",
                float(duration_s) if isinstance(duration_s, (int, float)) else None,
                int(file_size_bytes or 0),
                (note or "").strip(),
                analysis_json,
            ),
        )
        return int(cur.lastrowid)


def list_recent_audio_entries(limit: int = 50) -> List[Dict[str, Any]]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, diary_date, file_path, source_format, duration_s, file_size_bytes, note, analysis_json
            FROM audio_entries
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        item["analysis"] = _safe_json_loads(item.get("analysis_json") or "{}") or {}
        out.append(item)
    return out


def list_recent_audio_analyses(limit: int = 30) -> List[Dict[str, Any]]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT analysis_json
            FROM audio_entries
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        obj = _safe_json_loads(r["analysis_json"] or "{}")
        if isinstance(obj, dict):
            out.append(obj)
    return out

