from __future__ import annotations

import asyncio
import json

import pytest

from workers import analysis_worker


def _patch_main_db(monkeypatch) -> None:
    monkeypatch.setattr(analysis_worker.db, "init_db", lambda: None)
    monkeypatch.setattr(analysis_worker.db, "reset_stale_running_block_jobs", lambda *, stale_seconds: 0)
    monkeypatch.setattr(
        analysis_worker,
        "_job_stats",
        lambda: {"pending": 0, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 0},
    )


def test_main_defaults_to_one_shot_worker(monkeypatch, capsys):
    _patch_main_db(monkeypatch)
    calls: list[tuple[str, dict]] = []

    async def fake_run_once(**kwargs):
        calls.append(("once", kwargs))
        return {"processed": 1, "ok": 1, "failed": 0, "skipped": 0}

    async def fake_run_forever(**kwargs):
        calls.append(("forever", kwargs))
        return 0

    monkeypatch.setattr(analysis_worker, "run_once", fake_run_once)
    monkeypatch.setattr(analysis_worker, "run_forever", fake_run_forever)

    rc = analysis_worker.main(["--force", "--limit", "2"])

    assert rc == 0
    assert [kind for kind, _ in calls] == ["once"]
    assert calls[0][1]["limit"] == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["processed"] == 1
    assert "loop" not in payload


def test_main_loop_mode_is_explicit_opt_in(monkeypatch, capsys):
    _patch_main_db(monkeypatch)
    calls: list[tuple[str, dict]] = []

    async def fake_run_once(**kwargs):
        calls.append(("once", kwargs))
        return {"processed": 1, "ok": 1, "failed": 0, "skipped": 0}

    async def fake_run_forever(**kwargs):
        calls.append(("forever", kwargs))
        return 0

    monkeypatch.setattr(analysis_worker, "run_once", fake_run_once)
    monkeypatch.setattr(analysis_worker, "run_forever", fake_run_forever)

    rc = analysis_worker.main(["--force", "--loop", "--poll-seconds", "0.25"])

    assert rc == 0
    assert [kind for kind, _ in calls] == ["forever"]
    assert calls[0][1]["poll_seconds"] == 0.25
    assert capsys.readouterr().out == ""


def test_run_forever_reports_each_poll_without_infinite_test(monkeypatch, capsys):
    class StopLoop(Exception):
        pass

    stats = iter(
        [
            {"pending": 1, "running": 0, "done": 0, "failed": 0, "skipped": 0, "total": 1},
            {"pending": 0, "running": 0, "done": 1, "failed": 0, "skipped": 0, "total": 1},
        ]
    )
    sleep_seconds: list[float] = []

    monkeypatch.setattr(analysis_worker.db, "reset_stale_running_block_jobs", lambda *, stale_seconds: 3)
    monkeypatch.setattr(analysis_worker, "_job_stats", lambda: next(stats))

    async def fake_run_once(**kwargs):
        return {"processed": 0, "ok": 0, "failed": 0, "skipped": 0}

    async def fake_sleep(seconds):
        sleep_seconds.append(seconds)
        raise StopLoop()

    monkeypatch.setattr(analysis_worker, "run_once", fake_run_once)
    monkeypatch.setattr(analysis_worker.asyncio, "sleep", fake_sleep)

    with pytest.raises(StopLoop):
        asyncio.run(
            analysis_worker.run_forever(
                limit=5,
                max_attempts=3,
                retry_failed=False,
                timeout_s=0.0,
                job_timeout_s=30.0,
                stale_seconds=1800,
                backend="cloud",
                preferred_provider="deepseek",
                poll_seconds=0.25,
            )
        )

    payload = json.loads(capsys.readouterr().out)
    assert payload["loop"] is True
    assert payload["unstuck"] == 3
    assert payload["processed"] == 0
    assert payload["stats_before"]["pending"] == 1
    assert payload["stats_after"]["done"] == 1
    assert sleep_seconds == [1.0]
