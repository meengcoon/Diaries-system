from storage import db
from storage.repo_entries import get_entry
from services.analysis_jobs import prioritize_entry_jobs
from services.entry_ingest_service import replace_entry_content_atomic


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
    assert str(claimed["leased_by"]).startswith("analysis_worker")
    assert str(claimed["leased_until"])


def test_reset_stale_running_block_jobs_clears_expired_lease(isolated_db):
    entry_id = db.insert_entry(raw_text="x" * 200, source="test")
    block_id = db.insert_entry_block(entry_id=entry_id, idx=0, title="t", raw_text="x" * 200)
    db.insert_block_job(block_id=block_id, status="pending", attempts=0)

    claimed = db.claim_next_block_job(lease_seconds=30, lease_owner="worker:test")
    assert claimed is not None

    conn = db.connect()
    try:
        conn.execute(
            "UPDATE block_jobs SET leased_until=?, updated_at=? WHERE job_id=?",
            ("1970-01-01T00:00:00+00:00", "1970-01-01T00:00:00+00:00", int(claimed["job_id"])),
        )
        conn.commit()
    finally:
        conn.close()

    reset_n = db.reset_stale_running_block_jobs(stale_seconds=1800)
    assert reset_n == 1

    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT status, leased_by, leased_until, last_error FROM block_jobs WHERE job_id=?",
            (int(claimed["job_id"]),),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert str(row["status"]) == "failed"
    assert row["leased_by"] is None
    assert row["leased_until"] is None
    assert "lease expired" in str(row["last_error"] or "")


def test_claim_next_block_job_ignores_stale_entry_version(isolated_db):
    entry_id = db.insert_entry(raw_text="这是最初的内容。", source="test")
    current = get_entry(entry_id)
    rebuilt = replace_entry_content_atomic(
        entry_id=entry_id,
        raw_text="这是更新后的内容，会创建新的 block 和 job。",
        created_at=str((current or {}).get("created_at") or ""),
    )
    current_version = int(rebuilt["entry_version"])

    conn = db.connect()
    try:
        conn.execute(
            """
            UPDATE block_jobs
            SET entry_version=?, status='pending', attempts=0
            WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)
            """,
            (current_version - 1, int(entry_id)),
        )
        conn.commit()
    finally:
        conn.close()

    claimed = db.claim_next_block_job()
    assert claimed is None


def test_claim_next_block_job_skips_seen_ids_when_retry_failed(isolated_db):
    entry_id = db.insert_entry(raw_text="x" * 400, source="test")
    block_a = db.insert_entry_block(entry_id=entry_id, idx=0, title="a", raw_text="x" * 200)
    block_b = db.insert_entry_block(entry_id=entry_id, idx=1, title="b", raw_text="y" * 200)
    failed_job_id = db.insert_block_job(block_id=block_a, status="failed", attempts=1, last_error="first failure")
    db.insert_block_job(block_id=block_b, status="pending", attempts=0)

    claimed = db.claim_next_block_job(
        retry_failed=True,
        max_attempts=8,
        exclude_job_ids={failed_job_id},
    )

    assert claimed is not None
    assert int(claimed["block_id"]) == int(block_b)
    assert str(claimed["status"]) == "running"


def test_prioritize_entry_jobs_clears_lease_fields_on_reset(isolated_db):
    entry_id = db.insert_entry(raw_text="x" * 400, source="test")
    block_id = db.insert_entry_block(entry_id=entry_id, idx=0, title="a", raw_text="x" * 200)
    job_id = db.insert_block_job(block_id=block_id, status="running", attempts=3, leased_by="worker:test", leased_until="2099-01-01T00:00:00+00:00")

    pending_n = prioritize_entry_jobs(entry_id, force_reanalyze=True, max_attempts=8)

    assert pending_n == 1
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT status, attempts, leased_by, leased_until, last_error FROM block_jobs WHERE job_id=?",
            (int(job_id),),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert str(row["status"]) == "pending"
    assert int(row["attempts"] or 0) == 0
    assert row["leased_by"] is None
    assert row["leased_until"] is None
    assert row["last_error"] is None
