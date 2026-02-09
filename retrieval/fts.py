

from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional

# M3 retrieval helpers.
# Primary path: SQLite FTS5 (entry_fts)
# Fallback: deterministic LIKE search over entry_analysis.analysis_json (NOT raw_text)

try:
    # Prefer the canonical DB helpers.
    from storage.db import (
        get_entry_analysis_brief,
        search_entry_ids_fts,
    )
    # IMPORTANT: use the shared connection factory so PRAGMAs/timeout are consistent.
    from storage.db_core import _conn_ro
except ImportError:  # pragma: no cover
    # Fallback for running as a loose script.
    from db import (  # type: ignore
        get_entry_analysis_brief,
        search_entry_ids_fts,
    )
    from storage.db_core import _conn_ro  # type: ignore


_WORD_RE = re.compile(r"[0-9A-Za-z_\u4e00-\u9fff]+")


def _tokenize(q: str) -> List[str]:
    q = (q or "").strip().lower()
    if not q:
        return []
    toks = _WORD_RE.findall(q)
    # keep it small and stable
    toks = [t for t in toks if len(t) >= 2]
    return toks[:12]


def _to_fts_query(tokens: List[str]) -> str:
    """Build a conservative FTS query.

    - Quote tokens to reduce accidental operator injection.
    - Join with AND (space) so results are more precise and stable.
    """
    if not tokens:
        return ""
    safe = [t.replace('"', "") for t in tokens]
    return " ".join([f'"{t}"' for t in safe])


def fts_ready() -> bool:
    """True if the entry_fts table exists (FTS5 index built)."""
    with _conn_ro() as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry_fts'"
        ).fetchone()
        return bool(row)


def search_entry_ids(query: str, top_k: int = 6) -> List[int]:
    """Top-K entry ids for a query.

    Order must be stable for the same query.
    - Prefer FTS5 (bm25 + tie-breakers handled inside storage.db)
    - Fallback to LIKE over analysis_json with created_at/id tie-break
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    # 1) FTS path
    q_fts = _to_fts_query(tokens)
    if q_fts:
        ids = search_entry_ids_fts(q_fts, top_k=int(top_k))
        if ids:
            return ids

    # 2) Fallback path (deterministic, but less relevant)
    return search_entry_ids_like(tokens, top_k=int(top_k))


def search_entry_ids_like(tokens: List[str], top_k: int = 6) -> List[int]:
    """Fallback search over entry_analysis.analysis_json (NOT raw_text)."""
    if not tokens:
        return []

    with _conn_ro() as conn:
        # Require all tokens (AND) for precision and stability.
        where = " AND ".join(["a.analysis_json LIKE ?" for _ in tokens])
        params: List[Any] = [f"%{t}%" for t in tokens]
        params.append(int(top_k))

        rows = conn.execute(
            f"""
            SELECT e.id AS entry_id
            FROM entries e
            JOIN entry_analysis a ON a.entry_id = e.id
            WHERE {where}
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [int(r["entry_id"]) for r in rows]


def search_entries_brief(query: str, top_k: int = 6) -> List[Dict[str, Any]]:
    """Return compact analysis objects for Top-K results."""
    ids = search_entry_ids(query, top_k=top_k)
    out: List[Dict[str, Any]] = []
    for eid in ids:
        obj = get_entry_analysis_brief(int(eid))
        if obj:
            out.append(obj)
    return out


def rebuild_fts(limit: Optional[int] = None) -> Dict[str, Any]:
    """(Optional utility) Rebuild FTS index from existing entry_analysis.

    This is useful if you added FTS after you already had historical data.
    It is safe to call multiple times.
    """
    try:
        from storage.db import upsert_entry_fts  # type: ignore
    except Exception:  # pragma: no cover
        from db import upsert_entry_fts  # type: ignore

    with _conn_ro() as conn:
        if not fts_ready():
            return {"ok": False, "error": "entry_fts not available (FTS5 not compiled or table not created)"}

        rows = conn.execute(
            """
            SELECT e.id AS entry_id, e.created_at AS created_at, a.analysis_json AS analysis_json
            FROM entries e
            JOIN entry_analysis a ON a.entry_id = e.id
            ORDER BY e.created_at ASC, e.id ASC
            """
        ).fetchall()

        total = 0
        for r in rows:
            if limit is not None and total >= int(limit):
                break
            # analysis_json is stored as text; load minimal fields in db helper itself.
            import json

            analysis_obj = json.loads(r["analysis_json"]) if r["analysis_json"] else {}
            upsert_entry_fts(entry_id=int(r["entry_id"]), analysis_obj=analysis_obj, created_at=r["created_at"])
            total += 1

        return {"ok": True, "rebuilt": total}