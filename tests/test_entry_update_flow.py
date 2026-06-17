from __future__ import annotations

import asyncio

from pipeline.ingest import ingest_entry
from services.entry_ingest_service import replace_entry_content_atomic
from storage.db_core import connect
from storage.repo_entries import get_entry


def test_replace_entry_content_atomic_increments_version_and_replaces_jobs(isolated_db):
    res = asyncio.run(ingest_entry(text="第一段原文。\n\n第二段原文。", source="test"))
    entry_id = int(res["entry_id"])
    old_entry = get_entry(entry_id)
    assert old_entry is not None
    old_version = int(old_entry["version"])
    old_block_ids = {int(x) for x in (res.get("block_ids") or [])}

    replaced = replace_entry_content_atomic(
        entry_id=entry_id,
        raw_text="更新后的内容。\n\n这里是新的第二段。",
        created_at=str(old_entry["created_at"]),
    )

    new_entry = get_entry(entry_id)
    assert new_entry is not None
    assert int(new_entry["version"]) == old_version + 1
    assert int(replaced["entry_version"]) == int(new_entry["version"])
    assert int(replaced["queued_blocks"]) > 0

    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT b.block_id, b.raw_text, j.status, j.entry_version
            FROM entry_blocks b
            JOIN block_jobs j ON j.block_id = b.block_id
            WHERE b.entry_id=?
            ORDER BY b.idx ASC
            """,
            (entry_id,),
        ).fetchall()
    finally:
        conn.close()

    assert rows
    new_block_ids = {int(r["block_id"]) for r in rows}
    assert old_block_ids.isdisjoint(new_block_ids)
    assert all(str(r["status"]) == "pending" for r in rows)
    assert all(int(r["entry_version"]) == int(new_entry["version"]) for r in rows)
    assert any("更新后的内容" in str(r["raw_text"]) for r in rows)
