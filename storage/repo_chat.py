from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _utc_now_iso


def _row_dict(row: Any) -> dict:
    item = dict(row)
    raw = item.get("meta_json")
    if isinstance(raw, str) and raw:
        try:
            item["meta_json"] = json.loads(raw)
        except Exception:
            item["meta_json"] = None
    return item


def create_chat_session(
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    created_at: Optional[str] = None,
) -> int:
    created_at = created_at or _utc_now_iso()
    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chat_sessions(created_at, updated_at, title, summary)
            VALUES(?,?,?,?)
            """,
            (
                created_at,
                created_at,
                str(title or "新对话"),
                str(summary or "").strip() or None,
            ),
        )
        return int(cur.lastrowid)


def update_chat_session(
    session_id: int,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    updated_at: Optional[str] = None,
) -> None:
    if not session_id:
        return
    sets = []
    params: List[Any] = []
    if title is not None:
        sets.append("title=?")
        params.append(str(title or "新对话"))
    if summary is not None:
        sets.append("summary=?")
        params.append(str(summary or "").strip() or None)
    sets.append("updated_at=?")
    params.append(updated_at or _utc_now_iso())
    params.append(int(session_id))
    with _conn_txn() as conn:
        conn.execute(f"UPDATE chat_sessions SET {', '.join(sets)} WHERE id=?", params)


def get_chat_session(session_id: int) -> Optional[dict]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT id, created_at, updated_at, title, summary, pinned
            FROM chat_sessions
            WHERE id=?
            """,
            (int(session_id),),
        ).fetchone()
    return dict(row) if row else None


def list_chat_sessions(limit: int = 60) -> List[dict]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.created_at,
                s.updated_at,
                s.title,
                s.summary,
                s.pinned,
                (
                    SELECT text
                    FROM chat_messages m
                    WHERE m.session_id = s.id AND m.role='user'
                    ORDER BY m.created_at DESC, m.id DESC
                    LIMIT 1
                ) AS last_user_text,
                (
                    SELECT COUNT(1)
                    FROM chat_messages m
                    WHERE m.session_id = s.id
                ) AS message_count
            FROM chat_sessions s
            ORDER BY s.pinned DESC, s.updated_at DESC, s.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def list_chat_messages(session_id: int, limit: int = 200) -> List[dict]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT id, session_id, created_at, role, mode, text, meta_json
            FROM chat_messages
            WHERE session_id=?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (int(session_id), int(limit)),
        ).fetchall()
    return [_row_dict(r) for r in rows]


def insert_chat_message(
    *,
    session_id: Optional[int] = None,
    role: str,
    mode: str,
    text: str,
    created_at: Optional[str] = None,
    meta_json: Optional[Dict[str, Any]] = None,
) -> int:
    created_at = created_at or _utc_now_iso()
    payload = json.dumps(meta_json or {}, ensure_ascii=False) if meta_json is not None else None
    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chat_messages(session_id, created_at, role, mode, text, meta_json)
            VALUES(?,?,?,?,?,?)
            """,
            (
                int(session_id) if session_id else None,
                created_at,
                str(role or "user"),
                str(mode or "chat"),
                str(text or ""),
                payload,
            ),
        )
        if session_id:
            conn.execute(
                "UPDATE chat_sessions SET updated_at=? WHERE id=?",
                (created_at, int(session_id)),
            )
        return int(cur.lastrowid)


def list_recent_chat_messages(limit: int = 50, role: Optional[str] = None) -> List[dict]:
    with _conn_ro() as conn:
        if role:
            rows = conn.execute(
                """
                SELECT id, session_id, created_at, role, mode, text, meta_json
                FROM chat_messages
                WHERE role=?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (str(role), int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, session_id, created_at, role, mode, text, meta_json
                FROM chat_messages
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
    return [_row_dict(r) for r in rows]
