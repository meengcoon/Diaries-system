from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _fts_table_exists, _utc_now_iso


def upsert_entry_fts(
    *,
    entry_id: int,
    analysis_obj: Dict[str, Any],
    created_at: Optional[str] = None,
) -> None:
    """Upsert one entry into FTS index.

    - Indexes ONLY analysis fields (summary/topics/facts/todos)
    - Does not index raw_text
    - If FTS5 is unavailable, this becomes a no-op
    """
    with _conn_txn() as conn:
        if not _fts_table_exists(conn):
            return

        if not created_at:
            r = conn.execute("SELECT created_at FROM entries WHERE id=?", (int(entry_id),)).fetchone()
            created_at = (r[0] if r else None) or _utc_now_iso()

        summary = str((analysis_obj or {}).get("summary_1_3") or "").strip()

        topics = (analysis_obj or {}).get("topics") or []
        if not isinstance(topics, list):
            topics = []
        topics_text = " ".join([str(x).strip() for x in topics if str(x).strip()])

        facts = (analysis_obj or {}).get("facts") or []
        if not isinstance(facts, list):
            facts = []
        facts_text = " \n ".join([str(x).strip() for x in facts if str(x).strip()])

        todos = (analysis_obj or {}).get("todos") or []
        if not isinstance(todos, list):
            todos = []
        todos_text = " \n ".join([str(x).strip() for x in todos if str(x).strip()])

        # FTS5 virtual tables do not reliably support ON CONFLICT; do delete+insert.
        conn.execute("DELETE FROM entry_fts WHERE rowid=?", (int(entry_id),))
        conn.execute(
            "INSERT INTO entry_fts(rowid, entry_id, created_at, summary_1_3, topics, facts, todos) VALUES(?,?,?,?,?,?,?)",
            (int(entry_id), int(entry_id), str(created_at), summary, topics_text, facts_text, todos_text),
        )


def search_entry_ids_fts(query: str, top_k: int = 6) -> List[int]:
    """Return Top-K entry_ids matched by FTS5.

    Stable ordering: bm25 ASC (best first), then created_at DESC, then entry_id DESC.
    If FTS5 is unavailable, returns an empty list (caller can fallback).
    """
    q = (query or "").strip()
    if not q:
        return []

    with _conn_ro() as conn:
        if not _fts_table_exists(conn):
            return []

        try:
            rows = conn.execute(
                """
                SELECT rowid AS entry_id, bm25(entry_fts) AS score, created_at
                FROM entry_fts
                WHERE entry_fts MATCH ?
                ORDER BY score ASC, created_at DESC, entry_id DESC
                LIMIT ?
                """,
                (q, int(top_k)),
            ).fetchall()
            return [int(r["entry_id"]) for r in rows]
        except sqlite3.OperationalError:
            # e.g. older sqlite without bm25 support; treat as unavailable.
            return []
