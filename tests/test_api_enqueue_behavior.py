from __future__ import annotations
from pathlib import Path

from fastapi.testclient import TestClient

import api.routes_diary as routes_diary
import server
from pipeline.ingest import ingest_entry


def test_save_route_enqueues_analysis_without_background_tasks(monkeypatch, isolated_db, tmp_path):
    queued = []

    def _fake_queue_entry_analysis(**kwargs):
        queued.append(kwargs)
        return {"ok": True, "queued": True}

    monkeypatch.setattr(routes_diary, "queue_entry_analysis", _fake_queue_entry_analysis)
    monkeypatch.setattr(
        routes_diary,
        "append_daily_backup_entry",
        lambda **kwargs: Path(tmp_path) / "2026-04-11.txt",
    )
    server.app.state.ingest_entry = ingest_entry
    server.app.state.InputError = ValueError
    server.app.state.base_dir = Path(tmp_path)

    with TestClient(server.app) as client:
        res = client.post("/api/diary/save", json={"text": "Step 10 API enqueue test", "date": "2026-04-11"})

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["analysis_queued"] is True
    assert int(body["queued_blocks"]) > 0
    assert len(queued) == 1
    assert "background_tasks" not in queued[0]
    assert int(queued[0]["entry_id"]) == int(body["entry_id"])


def test_analyze_latest_route_only_enqueues(monkeypatch, isolated_db, tmp_path):
    queued = []

    def _fake_queue_latest_analysis(**kwargs):
        queued.append(kwargs)
        return {"ok": True, "queued": True}

    monkeypatch.setattr(routes_diary, "queue_latest_analysis", _fake_queue_latest_analysis)
    server.app.state.base_dir = Path(tmp_path)

    with TestClient(server.app) as client:
        res = client.post(
            "/api/diary/analyze_latest",
            json={
                "entry_limit": 10,
                "job_limit": 20,
                "preferred_provider": "deepseek",
                "min_block_chars": 20,
                "max_attempts": 8,
                "job_timeout_s": 180,
            },
        )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["queued"] is True
    assert len(queued) == 1
    assert int(queued[0]["entry_limit"]) == 10
    assert int(queued[0]["job_limit"]) == 20
