from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import server


def test_lifespan_startup_initializes_db(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(server, "init_db", lambda: calls.append("init"))
    monkeypatch.setattr(server.app.state, "ingest_entry", object())

    with TestClient(server.app):
        pass

    assert calls == ["init"]


def test_lifespan_preserves_ingest_unavailable_log(monkeypatch, caplog):
    monkeypatch.setattr(server, "init_db", lambda: None)
    monkeypatch.setattr(server.app.state, "ingest_entry", None)
    monkeypatch.setattr(server.app.state, "ingest_import_err", "ImportError: missing ingest")

    caplog.set_level(logging.ERROR, logger=server.logger.name)

    with TestClient(server.app):
        pass

    assert "ingest" in caplog.text
    assert "/api/diary/save" in caplog.text
    assert "ImportError: missing ingest" in caplog.text
