import sqlite3
import pytest

def _apply_min_contract_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("CREATE TABLE IF NOT EXISTS batches (batch_id TEXT PRIMARY KEY);")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS life_events (
            event_id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memo_ops (
            op_id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT
        );
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS changes (
            change_id INTEGER PRIMARY KEY,
            batch_id TEXT NOT NULL,
            FOREIGN KEY(batch_id) REFERENCES batches(batch_id) ON DELETE RESTRICT
        );
    """)

def test_foreign_keys_are_enforced(monkeypatch, tmp_path):
    db_path = tmp_path / "fk.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    from storage.db import transaction

    with transaction() as conn:
        _apply_min_contract_schema(conn)

    with pytest.raises(sqlite3.IntegrityError):
        with transaction() as conn:
            conn.execute("INSERT INTO memo_ops(op_id, batch_id) VALUES (?, ?)", (1, "missing"))

def test_single_transaction_no_half_writes(monkeypatch, tmp_path):
    db_path = tmp_path / "txn.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    from storage.db import connect, transaction

    with transaction() as conn:
        _apply_min_contract_schema(conn)

    class _Boom(Exception): pass

    with pytest.raises(_Boom):
        with transaction() as conn:
            conn.execute("INSERT INTO batches(batch_id) VALUES (?)", ("b1",))
            conn.execute("INSERT INTO life_events(event_id, batch_id) VALUES (?, ?)", (1, "b1"))
            conn.execute("INSERT INTO memo_ops(op_id, batch_id) VALUES (?, ?)", (1, "b1"))
            conn.execute("INSERT INTO changes(change_id, batch_id) VALUES (?, ?)", (1, "b1"))
            raise _Boom("force rollback")

    conn = connect()
    try:
        for table in ("batches", "life_events", "memo_ops", "changes"):
            n = conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0]
            assert n == 0
    finally:
        conn.close()