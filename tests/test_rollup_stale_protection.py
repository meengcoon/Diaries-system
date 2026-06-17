from __future__ import annotations

import json

from pipeline.rollup_entry import persist_entry_rollup
from storage.db_core import connect
from storage.repo_entries import get_entry, insert_entry
from storage.repo_jobs import insert_block_job, insert_entry_block, upsert_block_analysis


def _sample_analysis() -> dict:
    return {
        "summary_1_3": "今天主要在处理工作任务。",
        "open_insight": "压力还在，但整体是可控的。",
        "signals": {"mood": 6, "stress": 7, "sleep": None, "exercise": None, "social": None, "work": 8},
        "facts": ["完成了一项工作任务"],
        "todos": ["明天继续推进"],
        "topics": ["work"],
        "evidence_spans": [],
        "psychological_themes": [],
        "tensions": [],
        "needs": [],
        "patterns": [],
        "memory_candidates": [],
        "reflection_depth": 1,
    }


def test_persist_entry_rollup_ignores_stale_entry_version(isolated_db):
    entry_id = insert_entry(raw_text="今天主要在处理工作任务。", source="test")
    entry = get_entry(entry_id)
    assert entry is not None
    entry_version = int(entry["version"])

    block_id = insert_entry_block(
        entry_id=entry_id,
        idx=0,
        title="t",
        raw_text="今天主要在处理工作任务。",
        created_at=str(entry["created_at"]),
    )
    insert_block_job(block_id=block_id, entry_version=entry_version, status="done", attempts=1)
    upsert_block_analysis(
        block_id=block_id,
        analysis_json=json.dumps(_sample_analysis(), ensure_ascii=False),
        model="test-model",
        prompt_version="test-prompt",
        ok=True,
    )

    stale = persist_entry_rollup(entry_id, expected_entry_version=entry_version + 1)
    assert stale["ignored_stale"] is True
    assert stale["reason"] == "stale_entry_version"

    conn = connect()
    try:
        row = conn.execute("SELECT analysis_json FROM entry_analysis WHERE entry_id=?", (entry_id,)).fetchone()
    finally:
        conn.close()
    assert row is None


def test_persist_entry_rollup_is_stable_for_same_entry_version(isolated_db):
    entry_id = insert_entry(raw_text="今天主要在处理工作任务。", source="test")
    entry = get_entry(entry_id)
    assert entry is not None
    entry_version = int(entry["version"])

    block_id = insert_entry_block(
        entry_id=entry_id,
        idx=0,
        title="t",
        raw_text="今天主要在处理工作任务。",
        created_at=str(entry["created_at"]),
    )
    insert_block_job(block_id=block_id, entry_version=entry_version, status="done", attempts=1)
    upsert_block_analysis(
        block_id=block_id,
        analysis_json=json.dumps(_sample_analysis(), ensure_ascii=False),
        model="test-model",
        prompt_version="test-prompt",
        ok=True,
    )

    first = persist_entry_rollup(entry_id, expected_entry_version=entry_version)
    second = persist_entry_rollup(entry_id, expected_entry_version=entry_version)

    assert first["entry_version"] == entry_version
    assert second["entry_version"] == entry_version
    assert first["analysis_hash"] == second["analysis_hash"]

    conn = connect()
    try:
        row = conn.execute(
            "SELECT entry_version, analysis_hash FROM entry_analysis WHERE entry_id=?",
            (entry_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row["entry_version"]) == entry_version
    assert str(row["analysis_hash"]) == str(first["analysis_hash"])
