from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _safe_json_loads, _utc_now_iso, compute_sha256


def insert_entry(raw_text: str, created_at: Optional[str] = None, source: str = "api") -> int:
    """Always INSERT a new entry row and return its auto-increment id."""
    created_at = created_at or _utc_now_iso()
    raw_text = raw_text or ""
    sha = compute_sha256(raw_text.strip())

    with _conn_txn() as conn:
        cur = conn.execute(
            "INSERT INTO entries(created_at, raw_text, source, sha256) VALUES (?,?,?,?)",
            (created_at, raw_text, source, sha),
        )
        entry_id = int(cur.lastrowid)
    return entry_id


def save_entry_analysis(
    *,
    entry_id: int,
    analysis_json: str,
    model: str,
    prompt_version: str,
    created_at: Optional[str] = None,
) -> None:
    """Upsert analysis for one entry (1:1)."""
    created_at = created_at or _utc_now_iso()

    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO entry_analysis(entry_id, analysis_json, model, prompt_version, created_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET
                analysis_json=excluded.analysis_json,
                model=excluded.model,
                prompt_version=excluded.prompt_version,
                created_at=excluded.created_at
            """,
            (entry_id, analysis_json, model, prompt_version, created_at),
        )


def list_recent_entries(limit: int = 50) -> list[dict]:
    with _conn_ro() as conn:
        rows = conn.execute(
            "SELECT id, created_at, raw_text, source, sha256 FROM entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_recent_entry_summaries(n: int = 8) -> List[Dict[str, Any]]:
    """Return the most recent N entries in a compact form (NO raw_text)."""
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT e.id AS entry_id, e.created_at AS created_at, a.analysis_json AS analysis_json
            FROM entries e
            JOIN entry_analysis a ON a.entry_id = e.id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (int(n),),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        obj = _safe_json_loads(r["analysis_json"]) or {}
        out.append(
            {
                "entry_id": int(r["entry_id"]),
                "created_at": r["created_at"],
                "summary_1_3": obj.get("summary_1_3"),
                "topics": obj.get("topics") or [],
                "signals": obj.get("signals") or {},
            }
        )
    return out


def get_entry_analysis_brief(entry_id: int) -> Optional[Dict[str, Any]]:
    """Fetch one entry's analysis in a compact form suitable for context_pack."""
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT e.id AS entry_id, e.created_at AS created_at, a.analysis_json AS analysis_json
            FROM entries e
            JOIN entry_analysis a ON a.entry_id = e.id
            WHERE e.id=?
            """,
            (int(entry_id),),
        ).fetchone()

    if not row:
        return None

    obj = _safe_json_loads(row["analysis_json"]) or {}
    return {
        "entry_id": int(row["entry_id"]),
        "created_at": row["created_at"],
        "summary_1_3": obj.get("summary_1_3"),
        "topics": obj.get("topics") or [],
        "facts": obj.get("facts") or [],
        "todos": obj.get("todos") or [],
        "signals": obj.get("signals") or {},
    }
