import asyncio

from pipeline.ingest import ingest_entry
from storage import db


def test_ingest_enqueues_blocks_from_segment_text(monkeypatch, tmp_path):
    db_path = tmp_path / "ingest.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))

    db.init_db()

    text = "今天上班很累。\n\n晚上学英语。"
    res = asyncio.run(ingest_entry(text=text, source="test"))

    assert res["ok"] is True
    assert int(res["queued_blocks"]) > 0
    assert len(res["block_ids"]) == int(res["queued_blocks"])

    entry_id = int(res["entry_id"])
    blocks = db.list_entry_blocks(entry_id)
    assert len(blocks) == int(res["queued_blocks"])
    assert all((b.get("raw_text") or "").strip() for b in blocks)
