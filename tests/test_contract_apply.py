import time

import pytest

from pipeline.contract_apply import apply_result_contract
from pipeline.validators import ContractValidationError
from storage import db
from storage.db_core import connect


def _seed_block() -> int:
    entry_id = db.insert_entry(raw_text="seed", source="test")
    return db.insert_entry_block(entry_id=entry_id, idx=0, title="t", raw_text="seed")


def test_apply_result_contract_ok(monkeypatch, tmp_path):
    db_path = tmp_path / "apply_ok.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    db.init_db()

    block_id = _seed_block()
    now = int(time.time())
    payload = {
        "contract_version": "v1",
        "source": "cloud",
        "model_provider": "test",
        "model_name": "m",
        "blocks": [
            {
                "block_id": "le:ok1",
                "event_ts": now,
                "event_type": "test",
                "summary": "ok",
                "tags": [],
                "evidence_refs": [{"ref": f"block:{block_id}", "ts": now}],
                "memo_ops": [],
            }
        ],
    }

    out = apply_result_contract(payload)
    assert out["ok"] is True
    assert out["batch_id"]

    conn = connect()
    try:
        n = conn.execute("SELECT COUNT(*) AS n FROM life_events").fetchone()[0]
    finally:
        conn.close()
    assert int(n) == 1


def test_apply_result_contract_rejects_future_event(monkeypatch, tmp_path):
    db_path = tmp_path / "apply_future.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    db.init_db()
    block_id = _seed_block()

    future_ts = int(time.time()) + 3600
    payload = {
        "contract_version": "v1",
        "source": "cloud",
        "blocks": [
            {
                "block_id": "le:f1",
                "event_ts": future_ts,
                "event_type": "test",
                "tags": [],
                "evidence_refs": [{"ref": f"block:{block_id}", "ts": future_ts}],
                "memo_ops": [],
            }
        ],
    }

    with pytest.raises(ContractValidationError):
        apply_result_contract(payload)
