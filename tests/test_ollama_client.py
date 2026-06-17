from __future__ import annotations

import asyncio

from llm.ollama_client import OllamaClient


def test_ensure_server_available_does_not_autostart_by_default(monkeypatch):
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    checks = iter([False])
    spawned: list[list[str]] = []

    async def fake_is_server_available() -> bool:
        return next(checks)

    monkeypatch.delenv("OLLAMA_AUTOSTART", raising=False)
    monkeypatch.setattr(client, "is_server_available", fake_is_server_available)
    monkeypatch.setattr("llm.ollama_client.shutil.which", lambda name: f"/usr/local/bin/{name}")
    monkeypatch.setattr("llm.ollama_client.subprocess.Popen", lambda cmd, **kwargs: spawned.append(list(cmd)))

    ok = asyncio.run(client.ensure_server_available(startup_timeout_s=1.0))

    assert ok is False
    assert spawned == []


def test_ensure_server_available_autostarts_when_opted_in(monkeypatch):
    client = OllamaClient(base_url="http://127.0.0.1:11434")
    checks = iter([False, False, True])
    spawned: list[list[str]] = []

    async def fake_is_server_available() -> bool:
        return next(checks)

    monkeypatch.setattr(client, "is_server_available", fake_is_server_available)
    monkeypatch.setattr("llm.ollama_client.shutil.which", lambda name: f"/usr/local/bin/{name}")

    def fake_popen(cmd, **kwargs):
        spawned.append(list(cmd))

        class _Proc:
            pid = 1234

        return _Proc()

    monkeypatch.setattr("llm.ollama_client.subprocess.Popen", fake_popen)

    ok = asyncio.run(client.ensure_server_available(startup_timeout_s=1.0, autostart=True))

    assert ok is True
    assert spawned == [["/usr/local/bin/ollama", "serve"]]


def test_ensure_server_available_returns_false_without_binary(monkeypatch):
    client = OllamaClient(base_url="http://127.0.0.1:11434")

    async def fake_is_server_available() -> bool:
        return False

    monkeypatch.setattr(client, "is_server_available", fake_is_server_available)
    monkeypatch.setattr("llm.ollama_client.shutil.which", lambda name: None)

    ok = asyncio.run(client.ensure_server_available(startup_timeout_s=1.0, autostart=True))

    assert ok is False
