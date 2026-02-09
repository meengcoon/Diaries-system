from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from .db_core import connect, _conn_ro, _conn_txn, _parse_iso_utc, _utc_now_dt, _utc_now_iso


# =====================
# Step 1: blocks
# =====================

def insert_entry_block(
    *,
    entry_id: int,
    idx: int,
    title: Optional[str],
    raw_text: str,
    created_at: Optional[str] = None,
) -> int:
    """Insert one block for an entry; returns block_id.

    UNIQUE(entry_id, idx) prevents accidental duplicates on retries.
    """
    created_at = created_at or _utc_now_iso()
    raw_text = raw_text or ""

    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO entry_blocks(entry_id, idx, title, raw_text, created_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(entry_id, idx) DO UPDATE SET
                title=excluded.title,
                raw_text=excluded.raw_text,
                created_at=excluded.created_at
            """,
            (int(entry_id), int(idx), title, raw_text, created_at),
        )
        # If it was an UPDATE due to conflict, lastrowid may be 0; fetch the existing block_id.
        block_id = int(cur.lastrowid or 0)
        if block_id == 0:
            row = conn.execute(
                "SELECT block_id FROM entry_blocks WHERE entry_id=? AND idx=?",
                (int(entry_id), int(idx)),
            ).fetchone()
            block_id = int(row["block_id"]) if row else 0
    return block_id


def list_entry_blocks(entry_id: int) -> List[Dict[str, Any]]:
    """List blocks for an entry ordered by idx."""
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT block_id, entry_id, idx, title, raw_text, created_at
            FROM entry_blocks
            WHERE entry_id=?
            ORDER BY idx ASC
            """,
            (int(entry_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def count_entry_blocks(entry_id: int) -> int:
    with _conn_ro() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM entry_blocks WHERE entry_id=?",
            (int(entry_id),),
        ).fetchone()
    return int(row["n"] if row else 0)


def get_entry_block(block_id: int) -> Optional[Dict[str, Any]]:
    """Fetch one block by id."""
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT block_id, entry_id, idx, title, raw_text, created_at
            FROM entry_blocks
            WHERE block_id=?
            """,
            (int(block_id),),
        ).fetchone()
    return dict(row) if row else None


# =====================
# Step 1: block_jobs queue
# =====================

def insert_block_job(
    *,
    block_id: int,
    status: str = "pending",
    attempts: int = 0,
    last_error: Optional[str] = None,
    updated_at: Optional[str] = None,
    created_at: Optional[str] = None,
) -> int:
    """Create (or reset) a job for a block. Returns job_id.

    UNIQUE(block_id) ensures one active job row per block; retries reset status/attempts.
    """
    now = _utc_now_iso()
    created_at = created_at or now
    updated_at = updated_at or now

    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO block_jobs(block_id, status, attempts, last_error, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            ON CONFLICT(block_id) DO UPDATE SET
                status=excluded.status,
                attempts=excluded.attempts,
                last_error=excluded.last_error,
                updated_at=excluded.updated_at
            """,
            (int(block_id), str(status), int(attempts), last_error, created_at, updated_at),
        )
        job_id = int(cur.lastrowid or 0)
        if job_id == 0:
            row = conn.execute(
                "SELECT job_id FROM block_jobs WHERE block_id=?",
                (int(block_id),),
            ).fetchone()
            job_id = int(row["job_id"]) if row else 0
    return job_id


def count_block_jobs_by_status(status: str) -> int:
    with _conn_ro() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM block_jobs WHERE status=?",
            (str(status),),
        ).fetchone()
    return int(row["n"] if row else 0)


def list_pending_block_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """List pending jobs with block payload for a worker to consume later."""
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT
                j.job_id, j.block_id, j.status, j.attempts, j.last_error, j.updated_at,
                b.entry_id, b.idx, b.title, b.raw_text, b.created_at AS block_created_at
            FROM block_jobs j
            JOIN entry_blocks b ON b.block_id = j.block_id
            WHERE j.status='pending'
            ORDER BY j.updated_at ASC, j.job_id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


# =====================
# Step 2: worker queue consumption + block_analysis CRUD
# =====================

def reset_stale_running_block_jobs(stale_seconds: int = 1800) -> int:
    """Mark long-running jobs as failed so they can be retried.

    This prevents `running` from getting stuck forever if a worker crashes.
    """
    stale_seconds = int(stale_seconds)
    now = _utc_now_dt()
    now_s = now.isoformat(timespec="seconds")

    with _conn_txn() as conn:
        rows = conn.execute(
            "SELECT job_id, updated_at FROM block_jobs WHERE status='running'"
        ).fetchall()

        to_fail: List[int] = []
        for r in rows:
            updated_at = str(r["updated_at"])
            dt = _parse_iso_utc(updated_at)
            if dt is None:
                # If parsing fails, be conservative: do not touch it.
                continue
            age = (now - dt).total_seconds()
            if age >= stale_seconds:
                to_fail.append(int(r["job_id"]))

        if not to_fail:
            return 0

        # Bulk update
        qmarks = ",".join(["?"] * len(to_fail))
        conn.execute(
            f"""
            UPDATE block_jobs
            SET status='failed',
                last_error=?,
                updated_at=?
            WHERE job_id IN ({qmarks})
            """,
            (f"stale running > {stale_seconds}s", now_s, *to_fail),
        )
        return len(to_fail)


def claim_next_block_job(
    *,
    retry_failed: bool = False,
    max_attempts: int = 3,
) -> Optional[Dict[str, Any]]:
    """Atomically claim ONE job and return its full payload (job + block fields).

    - Claims from status='pending' (and optionally 'failed' when retry_failed=True)
    - Enforces attempts < max_attempts
    - Sets status='running', increments attempts, updates updated_at

    Returns None if no eligible job exists.
    """
    now_s = _utc_now_iso()
    max_attempts = int(max_attempts)

    # Use a dedicated connection so we can explicitly start BEGIN IMMEDIATE.
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")

        statuses = ["pending"]
        if retry_failed:
            statuses.append("failed")

        placeholders = ",".join(["?"] * len(statuses))
        row = conn.execute(
            f"""
            SELECT job_id, block_id, status, attempts
            FROM block_jobs
            WHERE status IN ({placeholders})
              AND attempts < ?
            ORDER BY updated_at ASC, job_id ASC
            LIMIT 1
            """,
            (*statuses, max_attempts),
        ).fetchone()

        if not row:
            conn.commit()
            return None

        job_id = int(row["job_id"])

        cur = conn.execute(
            """
            UPDATE block_jobs
            SET status='running',
                attempts=attempts+1,
                updated_at=?
            WHERE job_id=?
            """,
            (now_s, job_id),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return None

        payload = conn.execute(
            """
            SELECT
                j.job_id, j.block_id, j.status, j.attempts, j.last_error, j.updated_at,
                b.entry_id, b.idx, b.title, b.raw_text, b.created_at AS block_created_at
            FROM block_jobs j
            JOIN entry_blocks b ON b.block_id = j.block_id
            WHERE j.job_id=?
            """,
            (job_id,),
        ).fetchone()

        conn.commit()
        return dict(payload) if payload else None
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def mark_block_job_ok(job_id: int) -> None:
    now_s = _utc_now_iso()
    with _conn_txn() as conn:
        conn.execute(
            """
            UPDATE block_jobs
            SET status='done',
                last_error=NULL,
                updated_at=?
            WHERE job_id=?
            """,
            (now_s, int(job_id)),
        )


def mark_block_job_failed(job_id: int, last_error: str | None = None) -> None:
    """Mark a block job as failed (retriable)."""
    now_s = _utc_now_iso()
    with _conn_txn() as conn:
        conn.execute(
            """
            UPDATE block_jobs
            SET status='failed',
                last_error=?,
                updated_at=?
            WHERE job_id=?
            """,
            (last_error, now_s, int(job_id)),
        )


def mark_block_job_skipped(job_id: int, last_error: str | None = None) -> None:
    """Mark a block job as skipped (non-retryable input issue)."""
    now_s = _utc_now_iso()
    with _conn_txn() as conn:
        conn.execute(
            "UPDATE block_jobs SET status='skipped', last_error=?, updated_at=? WHERE job_id=?",
            (last_error, now_s, int(job_id)),
        )


def upsert_block_analysis(
    *,
    block_id: int,
    analysis_json: str,
    model: str,
    prompt_version: str,
    created_at: Optional[str] = None,
    ok: bool = True,
    error: Optional[str] = None,
) -> None:
    """Upsert analysis result for one block (1:1)."""
    created_at = created_at or _utc_now_iso()

    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO block_analysis(block_id, analysis_json, model, prompt_version, created_at, ok, error)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(block_id) DO UPDATE SET
                analysis_json=excluded.analysis_json,
                model=excluded.model,
                prompt_version=excluded.prompt_version,
                created_at=excluded.created_at,
                ok=excluded.ok,
                error=excluded.error
            """,
            (
                int(block_id),
                str(analysis_json),
                str(model),
                str(prompt_version),
                str(created_at),
                1 if ok else 0,
                error,
            ),
        )


def get_block_analysis(block_id: int) -> Optional[Dict[str, Any]]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT block_id, analysis_json, model, prompt_version, created_at, ok, error
            FROM block_analysis
            WHERE block_id=?
            """,
            (int(block_id),),
        ).fetchone()
    return dict(row) if row else None


# =====================
# Step 2+: entry-level rollups (blocks -> entry)
# =====================

def list_entry_blocks_with_analysis(entry_id: int) -> List[Dict[str, Any]]:
    """Return blocks for an entry together with their latest analysis + job status.

    This is used for entry-level rollups to avoid N+1 queries.
    """
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT
                b.block_id, b.entry_id, b.idx, b.title, b.raw_text, b.created_at AS block_created_at,
                j.job_id, j.status AS job_status, j.attempts, j.last_error, j.updated_at AS job_updated_at,
                a.analysis_json, a.model AS analysis_model, a.prompt_version AS analysis_prompt_version,
                a.created_at AS analysis_created_at, a.ok AS analysis_ok, a.error AS analysis_error
            FROM entry_blocks b
            LEFT JOIN block_jobs j ON j.block_id = b.block_id
            LEFT JOIN block_analysis a ON a.block_id = b.block_id
            WHERE b.entry_id=?
            ORDER BY b.idx ASC
            """,
            (int(entry_id),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_entry_job_status_summary(entry_id: int, *, max_attempts: int = 3) -> Dict[str, int]:
    """Return status counts for jobs that belong to one entry.

    The return dict includes:
      - pending/running/done/skipped
      - failed_retriable (failed AND attempts < max_attempts)
      - failed_exhausted (failed AND attempts >= max_attempts)
      - total
    """
    max_attempts = int(max_attempts)
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT j.status AS status, j.attempts AS attempts, COUNT(*) AS n
            FROM block_jobs j
            JOIN entry_blocks b ON b.block_id = j.block_id
            WHERE b.entry_id=?
            GROUP BY j.status, j.attempts
            """,
            (int(entry_id),),
        ).fetchall()

    out: Dict[str, int] = {
        "pending": 0,
        "running": 0,
        "done": 0,
        "skipped": 0,
        "failed_retriable": 0,
        "failed_exhausted": 0,
        "total": 0,
    }

    total = 0
    for r in rows:
        status = str(r["status"])
        attempts = int(r["attempts"] or 0)
        n = int(r["n"] or 0)
        total += n

        if status in ("pending", "running", "done", "skipped"):
            out[status] += n
        elif status == "failed":
            if attempts < max_attempts:
                out["failed_retriable"] += n
            else:
                out["failed_exhausted"] += n

    out["total"] = total
    return out
