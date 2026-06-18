from __future__ import annotations

import importlib
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from storage.db_core import connect, get_db_path

router = APIRouter()

JOB_STATUSES = ("pending", "running", "failed", "done", "skipped")
COUNT_TABLES = {"entries", "entry_blocks"}


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if table not in COUNT_TABLES:
        raise ValueError(f"unsupported health count table: {table}")
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"] if row else 0)


def _job_counts(conn: sqlite3.Connection) -> Dict[str, int]:
    counts: Dict[str, int] = {status: 0 for status in JOB_STATUSES}
    counts["total"] = 0
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM block_jobs GROUP BY status").fetchall()
    for row in rows:
        status = str(row["status"] or "")
        n = int(row["n"] or 0)
        if status in counts:
            counts[status] = n
        counts["total"] += n
    return counts


def _latest_rollup(conn: sqlite3.Connection) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT entry_id, analysis_json, model, prompt_version, entry_version, analysis_hash, created_at
        FROM entry_analysis
        ORDER BY created_at DESC, entry_id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return {"available": False, "entry_id": None}

    try:
        analysis_obj = json.loads(str(row["analysis_json"] or "{}"))
    except Exception:
        analysis_obj = {}
    if not isinstance(analysis_obj, dict):
        analysis_obj = {}

    return {
        "available": True,
        "entry_id": int(row["entry_id"]),
        "entry_version": int(row["entry_version"] or 0),
        "analysis_hash": str(row["analysis_hash"] or ""),
        "created_at": str(row["created_at"] or ""),
        "model": str(row["model"] or ""),
        "prompt_version": str(row["prompt_version"] or ""),
        "summary_1_3": str(analysis_obj.get("summary_1_3") or ""),
        "rollup_meta": analysis_obj.get("rollup_meta") if isinstance(analysis_obj.get("rollup_meta"), dict) else {},
    }


def _fts_status(conn: sqlite3.Connection) -> Dict[str, Any]:
    table_row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry_fts'"
    ).fetchone()
    table_exists = bool(table_row)
    usable = False
    error = ""
    if table_exists:
        try:
            conn.execute("SELECT rowid FROM entry_fts LIMIT 1").fetchone()
            usable = True
        except sqlite3.OperationalError as exc:
            error = f"{type(exc).__name__}: {exc}"

    return {
        "available": usable,
        "table_exists": table_exists,
        "error": error,
    }


def _context_pack_status() -> Dict[str, Any]:
    module_name = "services.retrieval_service"
    if importlib.util.find_spec(module_name) is None:
        return {"available": False, "module": module_name, "schema": "", "error": "module not found"}

    try:
        module = importlib.import_module(module_name)
        return {
            "available": True,
            "module": module_name,
            "schema": str(getattr(module, "SCHEMA_VERSION", "")),
            "error": "",
        }
    except Exception as exc:
        return {
            "available": False,
            "module": module_name,
            "schema": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _audio_status() -> Dict[str, Any]:
    module_name = "api.routes_audio"
    available = importlib.util.find_spec(module_name) is not None
    return {
        "available": available,
        "disabled": not available,
        "module": module_name,
        "checked_without_import": True,
    }


def build_health_summary() -> Dict[str, Any]:
    db_path = Path(get_db_path()).expanduser().resolve()
    conn = connect()
    try:
        entries_count = _count_table(conn, "entries")
        blocks_count = _count_table(conn, "entry_blocks")
        jobs = _job_counts(conn)
        latest_rollup = _latest_rollup(conn)
        fts = _fts_status(conn)
    finally:
        conn.close()

    context_pack = _context_pack_status()
    return {
        "ok": True,
        "db_path": str(db_path),
        "db": {
            "path": str(db_path),
            "exists": db_path.exists(),
        },
        "entries_count": entries_count,
        "blocks_count": blocks_count,
        "jobs": jobs,
        "latest_rollup": latest_rollup,
        "fts": fts,
        "fts_available": bool(fts.get("available")),
        "context_pack": context_pack,
        "context_pack_available": bool(context_pack.get("available")),
        "audio": _audio_status(),
    }


@router.get("/api/health")
async def health_summary():
    return build_health_summary()
