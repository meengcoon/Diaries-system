from __future__ import annotations

import json
from typing import Optional

from .db_core import _conn_ro, _conn_txn, _utc_now_iso


def get_mem_card(card_id: str) -> Optional[dict]:
    with _conn_ro() as conn:
        row = conn.execute(
            "SELECT card_id, type, content_json, updated_at, confidence FROM mem_cards WHERE card_id=?",
            (card_id,),
        ).fetchone()
    return dict(row) if row else None


def list_mem_cards(limit: int = 50, type: Optional[str] = None) -> list[dict]:
    with _conn_ro() as conn:
        if type:
            rows = conn.execute(
                "SELECT card_id, type, content_json, updated_at, confidence FROM mem_cards WHERE type=? ORDER BY updated_at DESC LIMIT ?",
                (type, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT card_id, type, content_json, updated_at, confidence FROM mem_cards ORDER BY updated_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
    return [dict(r) for r in rows]


def upsert_mem_card(
    *,
    card_id: str,
    type: str,
    content_json: dict,
    updated_at: Optional[str] = None,
    confidence: float = 0.5,
) -> None:
    updated_at = updated_at or _utc_now_iso()
    payload = json.dumps(content_json or {}, ensure_ascii=False)

    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO mem_cards(card_id, type, content_json, updated_at, confidence)
            VALUES(?,?,?,?,?)
            ON CONFLICT(card_id) DO UPDATE SET
                type=excluded.type,
                content_json=excluded.content_json,
                updated_at=excluded.updated_at,
                confidence=excluded.confidence
            """,
            (card_id, type, payload, updated_at, float(confidence)),
        )


def insert_mem_card_change(
    *,
    card_id: str,
    entry_id: int,
    diff_json: dict,
    created_at: Optional[str] = None,
) -> int:
    created_at = created_at or _utc_now_iso()
    payload = json.dumps(diff_json or {}, ensure_ascii=False)

    with _conn_txn() as conn:
        cur = conn.execute(
            "INSERT INTO mem_card_changes(card_id, entry_id, diff_json, created_at) VALUES(?,?,?,?)",
            (card_id, int(entry_id), payload, created_at),
        )
        change_id = int(cur.lastrowid)
    return change_id


def list_mem_card_changes(card_id: str, limit: int = 50) -> list[dict]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT change_id, card_id, entry_id, diff_json, created_at
            FROM mem_card_changes
            WHERE card_id=?
            ORDER BY change_id DESC
            LIMIT ?
            """,
            (card_id, int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
