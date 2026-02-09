from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .db_core import _conn_ro, _conn_txn, _safe_json_loads, _utc_now_iso


def _to_json_text(obj: Any) -> Optional[str]:
    """Serialize dict/list payloads to stable JSON text for storage.
    - None stays None
    - str stays str
    - dict/list -> json.dumps(sort_keys=True) for stable hashing/debugging
    """
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except Exception:
        return str(obj)


def insert_call(
    *,
    provider: str,
    model: str,
    prompt_version: str,
    request_hash: str,
    request_json: Any = None,
    response_json: Any = None,
    status: str = "ok",
    error: Optional[str] = None,
    ms: Optional[int] = None,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    tokens_total: Optional[int] = None,
    created_at: Optional[str] = None,
) -> int:
    """Insert one llm call audit row. Returns inserted id."""
    status = str(status or "").strip().lower()
    if status not in {"ok", "failed"}:
        status = "failed"
        error = error or "invalid status"

    created_at = created_at or _utc_now_iso()

    req_txt = _to_json_text(request_json)
    resp_txt = _to_json_text(response_json)

    with _conn_txn() as conn:
        cur = conn.execute(
            """
            INSERT INTO llm_calls(
                created_at, provider, model, prompt_version,
                request_hash, request_json, response_json,
                status, error, ms,
                tokens_prompt, tokens_completion, tokens_total
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                created_at,
                str(provider),
                str(model),
                str(prompt_version),
                str(request_hash),
                req_txt,
                resp_txt,
                status,
                error,
                int(ms) if ms is not None else None,
                int(tokens_prompt) if tokens_prompt is not None else None,
                int(tokens_completion) if tokens_completion is not None else None,
                int(tokens_total) if tokens_total is not None else None,
            ),
        )
        return int(cur.lastrowid)


def get_call(call_id: int) -> Optional[Dict[str, Any]]:
    with _conn_ro() as conn:
        row = conn.execute(
            """
            SELECT
                id, created_at, provider, model, prompt_version,
                request_hash, request_json, response_json,
                status, error, ms,
                tokens_prompt, tokens_completion, tokens_total
            FROM llm_calls
            WHERE id=?
            """,
            (int(call_id),),
        ).fetchone()

    if not row:
        return None

    return {
        "id": int(row["id"]),
        "created_at": row["created_at"],
        "provider": row["provider"],
        "model": row["model"],
        "prompt_version": row["prompt_version"],
        "request_hash": row["request_hash"],
        "request_json": _safe_json_loads(row["request_json"]) if row["request_json"] else None,
        "response_json": _safe_json_loads(row["response_json"]) if row["response_json"] else None,
        "status": row["status"],
        "error": row["error"],
        "ms": int(row["ms"]) if row["ms"] is not None else None,
        "tokens_prompt": int(row["tokens_prompt"]) if row["tokens_prompt"] is not None else None,
        "tokens_completion": int(row["tokens_completion"]) if row["tokens_completion"] is not None else None,
        "tokens_total": int(row["tokens_total"]) if row["tokens_total"] is not None else None,
    }


def list_calls(
    *,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    provider: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    newest_first: bool = True,
) -> List[Dict[str, Any]]:
    """List audit calls with basic filters.
    - time_min/time_max are ISO strings (same format as created_at)
    - provider/status optional
    """
    where: List[str] = []
    params: List[Any] = []

    if time_min:
        where.append("created_at >= ?")
        params.append(str(time_min))
    if time_max:
        where.append("created_at < ?")
        params.append(str(time_max))
    if provider:
        where.append("provider = ?")
        params.append(str(provider))
    if status:
        where.append("status = ?")
        params.append(str(status))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = "ORDER BY created_at DESC, id DESC" if newest_first else "ORDER BY created_at ASC, id ASC"

    with _conn_ro() as conn:
        rows = conn.execute(
            f"""
            SELECT
                id, created_at, provider, model, prompt_version,
                request_hash, request_json, response_json,
                status, error, ms,
                tokens_prompt, tokens_completion, tokens_total
            FROM llm_calls
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            (*params, int(limit), int(offset)),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "created_at": r["created_at"],
                "provider": r["provider"],
                "model": r["model"],
                "prompt_version": r["prompt_version"],
                "request_hash": r["request_hash"],
                "status": r["status"],
                "error": r["error"],
                "ms": int(r["ms"]) if r["ms"] is not None else None,
                "tokens_prompt": int(r["tokens_prompt"]) if r["tokens_prompt"] is not None else None,
                "tokens_completion": int(r["tokens_completion"]) if r["tokens_completion"] is not None else None,
                "tokens_total": int(r["tokens_total"]) if r["tokens_total"] is not None else None,
                "request_json": _safe_json_loads(r["request_json"]) if r["request_json"] else None,
                "response_json": _safe_json_loads(r["response_json"]) if r["response_json"] else None,
            }
        )
    return out