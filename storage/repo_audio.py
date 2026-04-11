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


def get_audio_entry(audio_id: int) -> Optional[Dict[str, Any]]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT id, created_at, diary_date, file_path, source_format, duration_s, file_size_bytes, note, analysis_json
            FROM audio_entries
            WHERE id=?
            LIMIT 1
            """,
            (int(audio_id),),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["analysis"] = _safe_json_loads(item.get("analysis_json") or "{}") or {}
    return item


def upsert_audio_content_link(
    *,
    audio_entry_id: int,
    entry_id: Optional[int],
    status: str,
    provider: str = "",
    error: Optional[str] = None,
    updated_at: Optional[str] = None,
    created_at: Optional[str] = None,
) -> None:
    now = _utc_now_iso()
    updated_at = updated_at or now
    created_at = created_at or now
    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO audio_content_links(
                audio_entry_id, entry_id, status, provider, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(audio_entry_id) DO UPDATE SET
                entry_id=excluded.entry_id,
                status=excluded.status,
                provider=excluded.provider,
                error=excluded.error,
                updated_at=excluded.updated_at
            """,
            (
                int(audio_entry_id),
                int(entry_id) if isinstance(entry_id, int) else None,
                str(status or "pending"),
                str(provider or ""),
                (error or None),
                created_at,
                updated_at,
            ),
        )


def get_audio_content_link(audio_entry_id: int) -> Optional[Dict[str, Any]]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT audio_entry_id, entry_id, status, provider, error, created_at, updated_at
            FROM audio_content_links
            WHERE audio_entry_id=?
            LIMIT 1
            """,
            (int(audio_entry_id),),
        ).fetchone()
    return dict(row) if row else None


def count_audio_entries_pending_content() -> int:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM audio_entries a
            LEFT JOIN audio_content_links l ON l.audio_entry_id = a.id
            WHERE l.audio_entry_id IS NULL OR l.status != 'done'
            """
        ).fetchone()
    return int(row["n"] if row else 0)


def list_audio_entries_pending_content(limit: int = 100) -> List[Dict[str, Any]]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT
                a.id, a.created_at, a.diary_date, a.file_path, a.source_format,
                a.duration_s, a.file_size_bytes, a.note, a.analysis_json,
                l.entry_id AS linked_entry_id, l.status AS linked_status, l.provider AS linked_provider, l.error AS linked_error
            FROM audio_entries a
            LEFT JOIN audio_content_links l ON l.audio_entry_id = a.id
            WHERE l.audio_entry_id IS NULL OR l.status != 'done'
            ORDER BY a.created_at ASC, a.id ASC
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
