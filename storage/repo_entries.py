from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _safe_json_loads, _utc_now_iso, compute_sha256


def insert_entry(raw_text: str, created_at: Optional[str] = None, source: str = "api") -> int:
    """Always INSERT a new entry row and return its auto-increment id."""
    created_at = created_at or _utc_now_iso()
    raw_text = raw_text or ""
    sha = compute_sha256(raw_text.strip())

    with _conn_txn() as conn:
        cur = conn.execute(
            "INSERT INTO entries(created_at, raw_text, source, sha256, version) VALUES (?,?,?,?,1)",
            (created_at, raw_text, source, sha),
        )
        entry_id = int(cur.lastrowid)
    return entry_id


def get_entry(entry_id: int) -> Optional[Dict[str, Any]]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT id, created_at, raw_text, source, sha256, version
            FROM entries
            WHERE id=?
            LIMIT 1
            """,
            (int(entry_id),),
        ).fetchone()
    return dict(row) if row else None


def list_entries_by_date(date_str: str) -> List[Dict[str, Any]]:
    prefix = f"{str(date_str or '').strip()}%"
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, raw_text, source, sha256, version
            FROM entries
            WHERE created_at LIKE ?
            ORDER BY created_at ASC, id ASC
            """,
            (prefix,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_entry_text(entry_id: int, raw_text: str) -> None:
    raw_text = raw_text or ""
    sha = compute_sha256(raw_text.strip())
    with _conn_txn() as conn:
        conn.execute(
            """
            UPDATE entries
            SET raw_text=?, sha256=?, version=COALESCE(version, 1) + 1
            WHERE id=?
            """,
            (raw_text, sha, int(entry_id)),
        )


def get_entry_version(entry_id: int) -> int:
    with _conn_ro() as conn:
        row = conn.execute("SELECT version FROM entries WHERE id=? LIMIT 1", (int(entry_id),)).fetchone()
    return int(row["version"] or 0) if row else 0


def delete_entry(entry_id: int) -> None:
    with _conn_txn() as conn:
        conn.execute("DELETE FROM entries WHERE id=?", (int(entry_id),))


def save_entry_analysis(
    *,
    entry_id: int,
    analysis_json: str,
    model: str,
    prompt_version: str,
    entry_version: Optional[int] = None,
    analysis_hash: Optional[str] = None,
    created_at: Optional[str] = None,
) -> None:
    """Upsert analysis for one entry (1:1)."""
    created_at = created_at or _utc_now_iso()
    if entry_version is None:
        entry_version = get_entry_version(int(entry_id))
    if analysis_hash is None:
        try:
            parsed = json.loads(str(analysis_json or "{}"))
            analysis_hash = compute_sha256(json.dumps(parsed, ensure_ascii=False, sort_keys=True))
        except Exception:
            analysis_hash = compute_sha256(str(analysis_json or ""))

    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO entry_analysis(entry_id, analysis_json, model, prompt_version, entry_version, analysis_hash, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET
                analysis_json=excluded.analysis_json,
                model=excluded.model,
                prompt_version=excluded.prompt_version,
                entry_version=excluded.entry_version,
                analysis_hash=excluded.analysis_hash,
                created_at=excluded.created_at
            """,
            (entry_id, analysis_json, model, prompt_version, int(entry_version or 0), str(analysis_hash or ""), created_at),
        )


def list_recent_entries(limit: int = 50) -> list[dict]:
    with _conn_ro() as conn:
        rows = conn.execute(
            "SELECT id, created_at, raw_text, source, sha256, version FROM entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_recent_entries_overview(limit: int = 50, *, max_attempts: int = 3) -> List[Dict[str, Any]]:
    """Return recent entries with list-view analysis/job summary in one query."""
    max_attempts = int(max_attempts)
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            WITH job_stats AS (
                SELECT
                    b.entry_id AS entry_id,
                    SUM(CASE WHEN j.status='pending' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN j.status='running' THEN 1 ELSE 0 END) AS running,
                    SUM(CASE WHEN j.status='done' THEN 1 ELSE 0 END) AS done,
                    SUM(CASE WHEN j.status='skipped' THEN 1 ELSE 0 END) AS skipped,
                    SUM(CASE WHEN j.status='failed' AND j.attempts < ? THEN 1 ELSE 0 END) AS failed_retriable,
                    SUM(CASE WHEN j.status='failed' AND j.attempts >= ? THEN 1 ELSE 0 END) AS failed_exhausted,
                    COUNT(*) AS total
                FROM entry_blocks b
                JOIN block_jobs j ON j.block_id = b.block_id
                GROUP BY b.entry_id
            )
            SELECT
                e.id,
                e.created_at,
                e.raw_text,
                e.source,
                e.sha256,
                e.version,
                a.analysis_json,
                COALESCE(js.pending, 0) AS pending,
                COALESCE(js.running, 0) AS running,
                COALESCE(js.done, 0) AS done,
                COALESCE(js.skipped, 0) AS skipped,
                COALESCE(js.failed_retriable, 0) AS failed_retriable,
                COALESCE(js.failed_exhausted, 0) AS failed_exhausted,
                COALESCE(js.total, 0) AS total,
                (
                    SELECT j.last_error
                    FROM entry_blocks b2
                    JOIN block_jobs j ON j.block_id = b2.block_id
                    WHERE b2.entry_id = e.id
                      AND j.status='failed'
                      AND COALESCE(j.last_error, '') <> ''
                    ORDER BY b2.idx ASC, j.updated_at DESC
                    LIMIT 1
                ) AS first_failure_error
            FROM entries e
            LEFT JOIN entry_analysis a ON a.entry_id = e.id
            LEFT JOIN job_stats js ON js.entry_id = e.id
            ORDER BY e.created_at DESC
            LIMIT ?
            """,
            (max_attempts, max_attempts, int(limit)),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        analysis_obj = _safe_json_loads(item.get("analysis_json") or "") or {}
        analysis_ready = bool(item.get("analysis_json"))
        if analysis_ready:
            analysis_status = "done"
        elif int(item.get("running") or 0) > 0:
            analysis_status = "running"
        elif int(item.get("pending") or 0) > 0:
            analysis_status = "pending"
        elif int(item.get("failed_retriable") or 0) > 0 or int(item.get("failed_exhausted") or 0) > 0:
            analysis_status = "failed"
        else:
            analysis_status = "idle"

        item["analysis_ready"] = analysis_ready
        item["analysis_status"] = analysis_status
        item["analysis_summary"] = str(analysis_obj.get("summary_1_3") or "")
        item["analysis_error"] = str(item.get("first_failure_error") or "")[:400]
        out.append(item)
    return out


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
                "open_insight": obj.get("open_insight"),
                "topics": obj.get("topics") or [],
                "patterns": obj.get("patterns") or [],
                "signals": obj.get("signals") or {},
                "analysis_quality": obj.get("analysis_quality") or {},
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
        "open_insight": obj.get("open_insight"),
        "topics": obj.get("topics") or [],
        "facts": obj.get("facts") or [],
        "todos": obj.get("todos") or [],
        "evidence_spans": obj.get("evidence_spans") or [],
        "reflection_depth": obj.get("reflection_depth"),
        "psychological_themes": obj.get("psychological_themes") or [],
        "tensions": obj.get("tensions") or [],
        "needs": obj.get("needs") or [],
        "patterns": obj.get("patterns") or [],
        "memory_candidates": obj.get("memory_candidates") or [],
        "signals": obj.get("signals") or {},
        "analysis_quality": obj.get("analysis_quality") or {},
    }


def is_memory_update_applied(*, entry_id: int, entry_version: int, analysis_hash: str) -> bool:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM memory_update_applied
            WHERE entry_id=? AND entry_version=? AND analysis_hash=?
            LIMIT 1
            """,
            (int(entry_id), int(entry_version), str(analysis_hash or "")),
        ).fetchone()
    return row is not None


def record_memory_update_applied(
    *,
    entry_id: int,
    entry_version: int,
    analysis_hash: str,
    created_at: Optional[str] = None,
) -> None:
    created_at = created_at or _utc_now_iso()
    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO memory_update_applied(entry_id, entry_version, analysis_hash, created_at)
            VALUES(?,?,?,?)
            ON CONFLICT(entry_id, entry_version) DO UPDATE SET
                analysis_hash=excluded.analysis_hash,
                created_at=excluded.created_at
            """,
            (int(entry_id), int(entry_version), str(analysis_hash or ""), created_at),
        )
