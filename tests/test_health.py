from __future__ import annotations

import json
import subprocess
import sys

from fastapi.testclient import TestClient

import server
from storage.repo_entries import insert_entry, save_entry_analysis
from storage.repo_fts import upsert_entry_fts
from storage.repo_jobs import insert_block_job, insert_entry_block


def test_health_endpoint_reports_empty_core_state(isolated_db):
    with TestClient(server.app) as client:
        res = client.get("/api/health")

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["db_path"] == str(isolated_db)
    assert body["entries_count"] == 0
    assert body["blocks_count"] == 0
    assert body["jobs"]["pending"] == 0
    assert body["jobs"]["running"] == 0
    assert body["jobs"]["failed"] == 0
    assert body["latest_rollup"]["available"] is False
    assert isinstance(body["fts"]["available"], bool)
    assert body["context_pack"]["available"] is True
    assert body["context_pack_available"] is True
    assert body["audio"]["checked_without_import"] is True


def test_health_endpoint_reports_entries_jobs_and_latest_rollup(isolated_db):
    entry_id = insert_entry(
        raw_text="health diagnostics entry",
        created_at="2026-06-18T10:00:00+00:00",
        source="test",
    )
    pending_block = insert_entry_block(
        entry_id=entry_id,
        idx=0,
        title=None,
        raw_text="pending",
        created_at="2026-06-18T10:00:00+00:00",
    )
    running_block = insert_entry_block(
        entry_id=entry_id,
        idx=1,
        title=None,
        raw_text="running",
        created_at="2026-06-18T10:00:00+00:00",
    )
    failed_block = insert_entry_block(
        entry_id=entry_id,
        idx=2,
        title=None,
        raw_text="failed",
        created_at="2026-06-18T10:00:00+00:00",
    )
    insert_block_job(block_id=pending_block, status="pending", attempts=0)
    insert_block_job(block_id=running_block, status="running", attempts=1)
    insert_block_job(block_id=failed_block, status="failed", attempts=2, last_error="boom")

    analysis = {
        "summary_1_3": "Health diagnostics rollup is available.",
        "topics": ["health"],
        "facts": ["diagnostics endpoint can see rollups"],
        "todos": [],
        "rollup_meta": {"blocks_total": 3, "blocks_ok": 1, "blocks_skipped": 0, "blocks_failed": 1},
    }
    save_entry_analysis(
        entry_id=entry_id,
        analysis_json=json.dumps(analysis),
        model="rollup",
        prompt_version="rollup_v1",
        entry_version=1,
        analysis_hash="health-hash",
        created_at="2026-06-18T10:05:00+00:00",
    )
    upsert_entry_fts(entry_id=entry_id, analysis_obj=analysis, created_at="2026-06-18T10:00:00+00:00")

    with TestClient(server.app) as client:
        res = client.get("/api/health")

    assert res.status_code == 200
    body = res.json()
    assert body["entries_count"] == 1
    assert body["blocks_count"] == 3
    assert body["jobs"]["pending"] == 1
    assert body["jobs"]["running"] == 1
    assert body["jobs"]["failed"] == 1
    assert body["jobs"]["total"] == 3
    assert body["latest_rollup"]["available"] is True
    assert body["latest_rollup"]["entry_id"] == entry_id
    assert body["latest_rollup"]["model"] == "rollup"
    assert body["latest_rollup"]["rollup_meta"]["blocks_total"] == 3


def test_health_route_import_does_not_load_audio_heavy_modules():
    code = """
import sys
import api.routes_health
loaded = set(sys.modules)
for name in ("pipeline.audio_features", "services.audio_ingest_service", "numpy", "faster_whisper"):
    if name in loaded:
        raise SystemExit(f"unexpected import: {name}")
print("ok")
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr or res.stdout
