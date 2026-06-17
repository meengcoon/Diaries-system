from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import server
from pipeline.ingest import MAX_CHARS, ingest_entry
from storage.db_core import connect, init_db


def _prepare_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DIARY_DB_PATH", str(tmp_path / "diary.sqlite3"))
    init_db()
    server.app.state.ingest_entry = ingest_entry
    server.app.state.InputError = ValueError
    server.app.state.base_dir = Path(tmp_path)
    server.app.state.data_dir = Path(tmp_path)


def _entry_count() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()
    return int(row["n"] if row else 0)


def test_save_rejects_empty_and_oversized_text_without_db_rows(monkeypatch, tmp_path):
    _prepare_app(monkeypatch, tmp_path)

    with TestClient(server.app) as client:
        empty_res = client.post("/api/diary/save", json={"text": "   ", "date": "2026-06-08"})
        too_long_res = client.post(
            "/api/diary/save",
            json={"text": "x" * (MAX_CHARS + 1), "date": "2026-06-08"},
        )

    assert empty_res.status_code == 400
    assert too_long_res.status_code == 413
    assert _entry_count() == 0


def test_save_accepts_exact_max_chars_and_enqueues_blocks(monkeypatch, tmp_path):
    _prepare_app(monkeypatch, tmp_path)
    text = "x" * MAX_CHARS

    with TestClient(server.app) as client:
        res = client.post("/api/diary/save", json={"text": text, "date": "2026-06-08"})

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert int(body["queued_blocks"]) > 0
    assert body["analysis_queued"] is True
    assert _entry_count() == 1
