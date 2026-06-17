from __future__ import annotations

import asyncio

from storage import db
from workers import analysis_worker
from block_analyze import AnalysisValidationError


class _DummyClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def test_run_once_uses_normalize_stage_error_as_top_level(monkeypatch, isolated_db):
    entry_id = db.insert_entry(raw_text="x" * 400, source="test")
    block_id = db.insert_entry_block(entry_id=entry_id, idx=0, title="t", raw_text="x" * 200)
    job_id = db.insert_block_job(block_id=block_id, status="pending", attempts=0)

    async def fake_analyze_block_cloud(*, title, raw_text, preferred_provider, stage_recorder):
        stage_recorder(
            stage="normalize",
            prompt_version="test:normalize",
            status="failed",
            input_json="{}",
            output_json=None,
            error="attempt 2/2: AnalysisValidationError: non-JSON output: bad comma at char 309",
            ms=None,
            model=None,
            backend_override=None,
        )
        raise AnalysisValidationError("normalize remained invalid after repair pass")

    monkeypatch.setattr(analysis_worker, "OllamaClient", _DummyClient)
    monkeypatch.setattr(analysis_worker, "analyze_block_cloud", fake_analyze_block_cloud)

    out = asyncio.run(
        analysis_worker.run_once(
            limit=1,
            max_attempts=8,
            retry_failed=True,
            timeout_s=0.0,
            job_timeout_s=30.0,
            backend="cloud",
            preferred_provider="deepseek",
        )
    )

    assert int(out["failed"]) == 1

    conn = db.connect()
    try:
        job_row = conn.execute(
            "SELECT status, last_error, leased_by, leased_until FROM block_jobs WHERE job_id=?",
            (int(job_id),),
        ).fetchone()
        analysis_row = conn.execute(
            "SELECT ok, error FROM block_analysis WHERE block_id=?",
            (int(block_id),),
        ).fetchone()
    finally:
        conn.close()

    expected = "attempt 2/2: AnalysisValidationError: non-JSON output: bad comma at char 309"
    assert job_row is not None
    assert analysis_row is not None
    assert str(job_row["status"]) == "failed"
    assert str(job_row["last_error"] or "") == expected
    assert job_row["leased_by"] is None
    assert job_row["leased_until"] is None
    assert int(analysis_row["ok"] or 0) == 0
    assert str(analysis_row["error"] or "") == expected
