import os, sqlite3, tempfile, pathlib, pytest

root = pathlib.Path(".").resolve()
schema = (root / "schema_v2.sql").read_text(encoding="utf-8")

def connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

with tempfile.TemporaryDirectory() as d:
    db_path = str(pathlib.Path(d) / "txn_test.sqlite3")

    # init schema
    c = connect(db_path)
    c.executescript(schema)
    c.commit()
    c.close()

    conn = connect(db_path)

    # Prepare a valid batch
    conn.execute("INSERT INTO batches(batch_id, contract_version) VALUES(?,?)", ("batch0001", "v1"))
    conn.commit()

    # 1) invalid FK must raise
    try:
        conn.execute(
            "INSERT INTO life_events(event_id,batch_id,block_id,event_ts,event_type,tags,evidence_refs) "
            "VALUES(?,?,?,?,?,?,?)",
            ("e_bad", "NO_SUCH_BATCH", "le:1", 1, "test", "[]", "[]"),
        )
        conn.commit()
        raise SystemExit("FAIL: expected FK failure, but insert succeeded")
    except sqlite3.IntegrityError:
        conn.rollback()
        print("PASS: invalid FK raises sqlite3.IntegrityError")

    # 2) txn atomic: write multiple rows then force failure, ensure rollback leaves no residue
    try:
        conn.execute("BEGIN")
        conn.execute(
            "INSERT INTO memo_ops(op_id,batch_id,card_key,op_type,payload_json,evidence_refs) "
            "VALUES(?,?,?,?,?,?)",
            ("op1", "batch1", "mc:test", "upsert", "{}", "[]"),
        )
        conn.execute(
            "INSERT INTO changes(change_id,batch_id,entity_type,entity_id,action,diff_json) "
            "VALUES(?,?,?,?,?,?)",
            ("c1", "batch1", "memo_ops", "op1", "create", "{}"),
        )

        # force failure: violate CHECK (json_valid(trigger_condition)...)
        conn.execute(
            "INSERT INTO memo_cards(card_key,card_type,content_json,trigger_condition) "
            "VALUES(?,?,?,?)",
            ("mc:oops", "t", "{\"x\":1}", "not_json"),
        )

        conn.commit()
        raise SystemExit("FAIL: expected CHECK failure, but commit succeeded")
    except sqlite3.IntegrityError:
        conn.rollback()

        mo = conn.execute("SELECT count(*) FROM memo_ops WHERE batch_id=?", ("batch1",)).fetchone()[0]
        ch = conn.execute("SELECT count(*) FROM changes WHERE batch_id=?", ("batch1",)).fetchone()[0]
        # memo_cards 这个失败了，不该有 mc:oops
        mc = conn.execute("SELECT count(*) FROM memo_cards WHERE card_key='mc:oops'").fetchone()[0]

        if (mo, ch, mc) == (0, 0, 0):
            print("PASS: rollback leaves no residue rows (no partial writes)")
        else:
            raise SystemExit(f"FAIL: residue rows exist: memo_ops={mo}, changes={ch}, memo_cards={mc}")

    conn.close()
    print("ALL PASS")