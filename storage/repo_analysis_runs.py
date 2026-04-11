from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _utc_now_iso


def insert_analysis_run(
    *,
    target_type: str,
    target_id: int,
    stage: str,
    backend: str,
    provider: Optional[str],
    model: Optional[str],
    prompt_version: str,
    status: str,
    input_json: Optional[str] = None,
    output_json: Optional[str] = None,
    error: Optional[str] = None,
    ms: Optional[int] = None,
    created_at: Optional[str] = None,
) -> int:
    created_at = created_at or _utc_now_iso()
    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO analysis_runs(
                target_type, target_id, stage, backend, provider, model,
                prompt_version, status, input_json, output_json, error, ms, created_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(target_type),
                int(target_id),
                str(stage),
                str(backend),
                provider,
                model,
                str(prompt_version),
                str(status),
                input_json,
                output_json,
                error,
                int(ms) if ms is not None else None,
                str(created_at),
            ),
        )
        return int(cur.lastrowid or 0)


def list_analysis_runs(
    *,
    target_type: str,
    target_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    with _conn_ro() as conn:
        rows = conn.execute(
            """
            SELECT
                id, target_type, target_id, stage, backend, provider, model,
                prompt_version, status, input_json, output_json, error, ms, created_at
            FROM analysis_runs
            WHERE target_type=? AND target_id=?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (str(target_type), int(target_id), int(limit)),
        ).fetchall()
    return [dict(r) for r in rows]
