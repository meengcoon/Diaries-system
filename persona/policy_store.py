from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from storage.db_core import connect
from utils.timeutil import utc_now_iso


def init_policy_store() -> None:
    conn = connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS persona_policies (
                version INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_json TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_persona_policies_active ON persona_policies(active);")
        conn.commit()
    finally:
        conn.close()


def save_policy(profile: Dict[str, Any], *, activate: bool = True) -> int:
    init_policy_store()
    conn = connect()
    try:
        if activate:
            conn.execute("UPDATE persona_policies SET active=0 WHERE active=1")
        cur = conn.execute(
            "INSERT INTO persona_policies(profile_json, active, created_at) VALUES(?,?,?)",
            (json.dumps(profile or {}, ensure_ascii=False), 1 if activate else 0, utc_now_iso()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def get_active_policy() -> Optional[Dict[str, Any]]:
    init_policy_store()
    conn = connect()
    try:
        row = conn.execute(
            """
            SELECT version, profile_json, created_at
            FROM persona_policies
            WHERE active=1
            ORDER BY version DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        return {
            "version": int(row["version"]),
            "profile": json.loads(row["profile_json"]),
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def list_policies(limit: int = 20) -> List[Dict[str, Any]]:
    init_policy_store()
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT version, profile_json, active, created_at
            FROM persona_policies
            ORDER BY version DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "version": int(r["version"]),
                    "active": bool(int(r["active"])),
                    "profile": json.loads(r["profile_json"]),
                    "created_at": r["created_at"],
                }
            )
        return out
    finally:
        conn.close()
