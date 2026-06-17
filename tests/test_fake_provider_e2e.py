from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

import server
from block_analyze import BlockAnalyzeResult
from pipeline.context_pack import build_context_pack
from pipeline.ingest import ingest_entry
from retrieval.fts import search_entries_brief
from storage.db_core import connect, init_db
from workers import analysis_worker


class _DummyClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _fake_analysis(raw_text: str) -> dict:
    return {
        "summary_1_3": "Fake provider captured alpha_project progress and a stress checkpoint.",
        "open_insight": "The entry shows a concrete project thread that can be retrieved later.",
        "signals": {
            "mood": 6,
            "stress": 7,
            "sleep": None,
            "exercise": None,
            "social": None,
            "work": 8,
        },
        "facts": ["alpha_project reached fake-provider E2E coverage"],
        "todos": ["review alpha_project next action"],
        "topics": ["alpha_project", "fake_provider", "work"],
        "evidence_spans": [raw_text[:60]],
        "psychological_themes": ["follow-through"],
        "tensions": ["speed vs coverage"],
        "needs": ["reliable feedback loop"],
        "patterns": ["uses tests to stabilize product behavior"],
        "memory_candidates": ["alpha_project is important enough to retrieve"],
        "reflection_depth": 2,
    }


def test_fake_provider_e2e_save_worker_rollup_retrieval(monkeypatch, tmp_path):
    monkeypatch.setenv("DIARY_DB_PATH", str(tmp_path / "diary.sqlite3"))
    init_db()
    server.app.state.ingest_entry = ingest_entry
    server.app.state.InputError = ValueError
    server.app.state.base_dir = Path(tmp_path)
    server.app.state.data_dir = Path(tmp_path)

    async def fake_analyze_block_cloud(*, title, raw_text, preferred_provider, stage_recorder):
        analysis = _fake_analysis(str(raw_text))
        output_json = json.dumps(analysis, ensure_ascii=False)
        for stage in ("evidence", "deep", "normalize", "final"):
            stage_recorder(
                stage=stage,
                prompt_version=f"fake:{stage}",
                status="ok",
                input_json=json.dumps({"title": title, "chars": len(str(raw_text))}, ensure_ascii=False),
                output_json=output_json,
                error=None,
                ms=1,
                model="fake:provider",
                backend_override="fake",
            )
        return BlockAnalyzeResult(analysis=analysis, ms=1, raw_output=output_json)

    async def fake_update_mem_cards_for_entry(**kwargs):
        return {
            "attempted": True,
            "ok": True,
            "updated": 0,
            "changes": 0,
            "card_ids": [],
            "ms": 0,
        }

    monkeypatch.setattr(analysis_worker, "OllamaClient", _DummyClient)
    monkeypatch.setattr(analysis_worker, "analyze_block_cloud", fake_analyze_block_cloud)
    monkeypatch.setattr(analysis_worker, "update_mem_cards_for_entry", fake_update_mem_cards_for_entry)

    text = (
        "alpha_project fake provider E2E entry. "
        "Today I checked whether saving, worker processing, rollup, FTS, dashboard, "
        "and context pack retrieval can all agree on the same analyzed diary thread. "
    ) * 6

    with TestClient(server.app) as client:
        save_res = client.post("/api/diary/save", json={"text": text, "date": "2026-06-08"})
        assert save_res.status_code == 200
        saved = save_res.json()
        entry_id = int(saved["entry_id"])
        assert saved["analysis_queued"] is True

        worker_out = asyncio.run(
            analysis_worker.run_once(
                limit=20,
                max_attempts=8,
                retry_failed=True,
                timeout_s=0.0,
                job_timeout_s=30.0,
                backend="cloud",
                preferred_provider="deepseek",
            )
        )
        assert int(worker_out["ok"]) == int(saved["queued_blocks"])
        assert worker_out["rollups"]

        detail_res = client.get(f"/api/diary/entry?id={entry_id}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["analysis_ready"] is True
        assert detail["analysis_status"] == "done"
        assert int(detail["job_stats"]["done"]) == int(saved["queued_blocks"])
        assert "alpha_project" in detail["analysis"]["topics"]
        assert detail["analysis_pipeline"]["has_staged_runs"] is True

        overview_res = client.get("/api/dashboard/overview?limit=90")
        assert overview_res.status_code == 200
        assert "alpha_project" in overview_res.json()["focus_lines"]

        list_res = client.get("/api/diary/list?limit=10")
        assert list_res.status_code == 200
        item = next(x for x in list_res.json()["items"] if int(x["entry_id"]) == entry_id)
        assert item["analysis_status"] == "done"

    fts_hits = search_entries_brief("alpha_project", top_k=5)
    assert any(int(x["entry_id"]) == entry_id for x in fts_hits)

    context_pack = build_context_pack("alpha_project", top_k=5, recent_n=5)
    assert any(int(x["entry_id"]) == entry_id for x in context_pack["topk"])
    assert any(int(x["entry_id"]) == entry_id for x in context_pack["recent"])

    with connect() as conn:
        analysis_row = conn.execute(
            "SELECT analysis_json FROM entry_analysis WHERE entry_id=?",
            (entry_id,),
        ).fetchone()
        job_counts = {
            str(row["status"]): int(row["n"])
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM block_jobs GROUP BY status").fetchall()
        }
    assert analysis_row is not None
    full_analysis = json.loads(str(analysis_row["analysis_json"] or "{}"))
    assert full_analysis["rollup_meta"]["blocks_ok"] == int(saved["queued_blocks"])
    assert job_counts.get("pending", 0) == 0
    assert job_counts.get("running", 0) == 0
