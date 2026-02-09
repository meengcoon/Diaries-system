import os
import pathlib
import sqlite3
import tempfile
import time

import pytest

from storage.db_core import connect
from storage import db
from pipeline.process_contract import ContractValidationError, process_contract


def _init_db(db_path: pathlib.Path) -> None:
    os.environ["DIARY_DB_PATH"] = str(db_path)
    schema = (pathlib.Path(".").resolve() / "schema_v2.sql").read_text(encoding="utf-8")

    c = connect()
    c.executescript(schema)
    c.commit()
    c.close()


def test_process_contract_minimal_ok():
    with tempfile.TemporaryDirectory() as d:
        db_path = pathlib.Path(d) / "contract_ok.sqlite3"
        _init_db(db_path)

        payload = {
            "contract_version": "v1",
            "source": "cloud",
            "model_provider": "test",
            "model_name": "m",
            "blocks": [
                {
                    "block_id": "le:1",
                    "event_ts": 1,
                    "event_type": "test",
                    "summary": "hello",
                    "tags": [],
                    "evidence_refs": [],
                    "memo_ops": [
                        {
                            "card_key": "mc:test",
                            "op_type": "upsert",
                            "payload": {"x": 1},
                            "evidence_refs": [],
                        }
                    ],
                }
            ],
        }

        batch_id = process_contract(payload)
        assert isinstance(batch_id, str) and len(batch_id) >= 8

        conn = connect()
        le = conn.execute("SELECT count(*) FROM life_events WHERE batch_id=?", (batch_id,)).fetchone()[0]
        mo = conn.execute("SELECT count(*) FROM memo_ops WHERE batch_id=?", (batch_id,)).fetchone()[0]
        ch = conn.execute("SELECT count(*) FROM changes WHERE batch_id=?", (batch_id,)).fetchone()[0]
        conn.close()

        assert (le, mo) == (1, 1)
        assert ch >= 2


def test_process_contract_future_evidence_rejected_and_atomic():
    with tempfile.TemporaryDirectory() as d:
        db_path = pathlib.Path(d) / "contract_future.sqlite3"
        _init_db(db_path)

        future_ts = int(time.time()) + 3600
        payload = {
            "contract_version": "v1",
            "source": "cloud",
            "blocks": [
                {
                    "block_id": "le:1",
                    "event_ts": 10,
                    "event_type": "test",
                    "tags": [],
                    "evidence_refs": [{"ref": "url:https://example.com", "ts": future_ts}],
                }
            ],
        }

        with pytest.raises(ContractValidationError):
            process_contract(payload)

        conn = connect()
        b = conn.execute("SELECT count(*) FROM batches").fetchone()[0]
        le = conn.execute("SELECT count(*) FROM life_events").fetchone()[0]
        mo = conn.execute("SELECT count(*) FROM memo_ops").fetchone()[0]
        ch = conn.execute("SELECT count(*) FROM changes").fetchone()[0]
        conn.close()

        assert (b, le, mo, ch) == (0, 0, 0, 0)


def test_process_contract_block_evidence_ref_ok():
    with tempfile.TemporaryDirectory() as d:
        db_path = pathlib.Path(d) / "contract_block_ref.sqlite3"
        _init_db(db_path)

        # Create core app tables too (entries/entry_blocks), then seed one block.
        db.init_db()
        entry_id = db.insert_entry(raw_text="seed block", source="test")
        block_id = db.insert_entry_block(entry_id=entry_id, idx=0, title="t", raw_text="seed block")

        payload = {
            "contract_version": "v1",
            "source": "cloud",
            "blocks": [
                {
                    "block_id": "le:1",
                    "event_ts": 10,
                    "event_type": "test",
                    "tags": [],
                    "evidence_refs": [{"ref": f"block:{block_id}", "ts": 10}],
                }
            ],
        }

        batch_id = process_contract(payload)
        assert isinstance(batch_id, str) and len(batch_id) >= 8
