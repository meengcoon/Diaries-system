from __future__ import annotations

from storage.db_core import connect


def prioritize_entry_jobs(entry_id: int, *, force_reanalyze: bool, max_attempts: int) -> int:
    conn = connect()
    try:
        conn.execute("BEGIN;")
        ancient = "1970-01-01T00:00:00+00:00"
        if force_reanalyze:
            conn.execute(
                """
                UPDATE block_jobs
                SET status='pending', attempts=0, last_error=NULL, updated_at=?
                WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)
                """,
                (ancient, int(entry_id)),
            )
            conn.execute(
                """
                DELETE FROM block_analysis
                WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)
                """,
                (int(entry_id),),
            )
        else:
            conn.execute(
                """
                UPDATE block_jobs
                SET status='pending',
                    attempts=CASE WHEN attempts>=? THEN 0 ELSE attempts END,
                    last_error=NULL,
                    updated_at=?
                WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)
                  AND status IN ('pending', 'failed', 'running')
                """,
                (max(1, int(max_attempts)), ancient, int(entry_id)),
            )

        row = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM block_jobs
            WHERE status='pending'
              AND block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)
            """,
            (int(entry_id),),
        ).fetchone()
        conn.commit()
        return int(row["n"]) if row else 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
