from storage import db


def test_claim_next_block_job_does_not_nested_begin(monkeypatch, tmp_path):
    db_path = tmp_path / "jobs.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))

    db.init_db()

    entry_id = db.insert_entry(raw_text="x" * 200, source="test")
    block_id = db.insert_entry_block(entry_id=entry_id, idx=0, title="t", raw_text="x" * 200)
    db.insert_block_job(block_id=block_id, status="pending", attempts=0)

    claimed = db.claim_next_block_job()
    assert claimed is not None
    assert int(claimed["block_id"]) == int(block_id)
    assert str(claimed["status"]) == "running"
    assert int(claimed["attempts"]) == 1
