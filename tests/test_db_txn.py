import os
import sqlite3
import pathlib
import tempfile
import pytest

from storage.db_core import connect, transaction

def test_fk_enforced_and_txn_atomic():
    root = pathlib.Path(".").resolve()
    schema = (root / "schema_v2.sql").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as d:
        db_path = pathlib.Path(d) / "txn_test.sqlite3"
        os.environ["DIARY_DB_PATH"] = str(db_path)

        # init schema
        c = connect()
        c.executescript(schema)
        c.commit()
        c.close()

        # 1) invalid FK must raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            with transaction() as conn:
                conn.execute(
                    "INSERT INTO life_events(event_id,batch_id,block_id,event_ts,event_type,tags,evidence_refs) "
                    "VALUES('e_fk','batch_not_exist','le:1',1,'test','[]','[]')"
                )

        # 2) rollback: no partial writes
        batch_id = "batch_txn_1"
        try:
            with transaction() as conn:
                conn.execute("INSERT INTO batches(batch_id,contract_version) VALUES(?, 'v1')", (batch_id,))
                conn.execute(
                    "INSERT INTO life_events(event_id,batch_id,block_id,event_ts,event_type,tags,evidence_refs) "
                    "VALUES(?, ?, 'le:1', 123, 'test', '[]', '[]')",
                    ("e1", batch_id),
                )
                conn.execute(
                    "INSERT INTO memo_ops(op_id,batch_id,card_key,op_type,payload_json,created_at) "
                    "VALUES('op1', ?, 'mc:test', 'upsert', '{\"x\":1}', 123)",
                    (batch_id,),
                )
                conn.execute(
                    "INSERT INTO changes(change_id,batch_id,entity_type,entity_id,action,diff_json,created_at) "
                    "VALUES('ch1', ?, 'memo_ops', 'op1', 'create', '{\"x\":1}', 123)",
                    (batch_id,),
                )
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        conn = connect()
        le = conn.execute("SELECT count(*) FROM life_events WHERE batch_id=?", (batch_id,)).fetchone()[0]
        mo = conn.execute("SELECT count(*) FROM memo_ops WHERE batch_id=?", (batch_id,)).fetchone()[0]
        ch = conn.execute("SELECT count(*) FROM changes WHERE batch_id=?", (batch_id,)).fetchone()[0]
        conn.close()

        assert (le, mo, ch) == (0, 0, 0)