from __future__ import annotations

from fastapi.testclient import TestClient

import api.routes_chat as routes_chat
import server
from storage.db_core import init_db


def test_voice_chat_rejects_oversized_upload_before_stt(monkeypatch, tmp_path):
    monkeypatch.setenv("DIARY_DB_PATH", str(tmp_path / "test.sqlite3"))
    init_db()
    monkeypatch.setattr(routes_chat, "MAX_VOICE_CHAT_UPLOAD_BYTES", 4)
    monkeypatch.setattr(server.app.state, "bot", object())

    with TestClient(server.app) as client:
        res = client.post(
            "/api/voice/chat",
            files={"audio": ("voice.webm", b"0123456789", "audio/webm")},
        )

    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "AUDIO_TOO_LARGE"
