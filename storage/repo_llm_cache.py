from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from storage.db_core import _conn_ro, _conn_txn, _parse_iso_utc, _safe_json_loads, _utc_now_iso


def _env_bool(name: str, default: bool) -> bool:
    val = (os.getenv(name) or "").strip().lower()
    if not val:
        return default
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return default


def is_cache_enabled() -> bool:
    """
    Env:
      - LLM_CACHE_ENABLED: 1/0 (default: 1)
    """
    return _env_bool("LLM_CACHE_ENABLED", True)


def make_cache_key(provider: str, model: str, request_hash: str) -> str:
    # Normalize for stable keys.
    return f"{provider}:{model}:{request_hash}".lower()


def get_cached_response_json(
    provider: str,
    model: str,
    request_hash: str,
    *,
    ttl_s: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    """
    Return cached response payload JSON dict or None.

    - If cache disabled, always returns None.
    - TTL (seconds) is optional; when provided it is checked against `updated_at`.
    """
    if enabled is None:
        enabled = is_cache_enabled()
    if not enabled:
        return None

    cache_key = make_cache_key(provider, model, request_hash)
    with _conn_ro() as conn:
        row = conn.execute(
            "SELECT response_json, updated_at FROM llm_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()

    if not row:
        return None

    if ttl_s is not None:
        updated_at = _parse_iso_utc(row["updated_at"]) if row["updated_at"] else None
        if updated_at is not None:
            now = datetime.now(timezone.utc)
            if updated_at + timedelta(seconds=int(ttl_s)) < now:
                return None

    payload = _safe_json_loads(row["response_json"]) if row["response_json"] else None
    return payload if isinstance(payload, dict) else None


def upsert_cached_response_json(
    provider: str,
    model: str,
    request_hash: str,
    response_json: dict[str, Any],
    *,
    enabled: Optional[bool] = None,
) -> str:
    """Insert/replace cached response payload; returns cache_key."""
    if enabled is None:
        enabled = is_cache_enabled()

    cache_key = make_cache_key(provider, model, request_hash)
    if not enabled:
        return cache_key

    now = _utc_now_iso()
    # Stable encoding helps debugging and makes diffs easier to read.
    payload_s = json.dumps(response_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    with _conn_txn() as conn:
        conn.execute(
            """
            INSERT INTO llm_cache(cache_key, provider, model, response_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                provider=excluded.provider,
                model=excluded.model,
                response_json=excluded.response_json,
                updated_at=excluded.updated_at
            """,
            (cache_key, provider, model, payload_s, now, now),
        )

    return cache_key


def delete_cache(provider: str, model: str, request_hash: str) -> None:
    cache_key = make_cache_key(provider, model, request_hash)
    with _conn_txn() as conn:
        conn.execute("DELETE FROM llm_cache WHERE cache_key=?", (cache_key,))


def purge_cache_older_than(days: int) -> int:
    """Best-effort cleanup; returns deleted rows."""
    if days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat(timespec="seconds")
    with _conn_txn() as conn:
        cur = conn.execute("DELETE FROM llm_cache WHERE updated_at < ?", (cutoff_iso,))
        return int(cur.rowcount or 0)