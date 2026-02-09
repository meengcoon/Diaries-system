from sync.client import LocalSyncService, SyncClient
from sync.events import detect_conflicts


def test_sync_conflict_detection(tmp_path):
    svc = LocalSyncService(str(tmp_path / "sync.sqlite3"))

    a = SyncClient(service=svc, device_id="dev_a")
    b = SyncClient(service=svc, device_id="dev_b")

    a.bootstrap_group()
    a.share_key_with_device(
        target_device_id="dev_b",
        target_public_key_b64=b.keys.public_key_b64,
    )
    assert b.fetch_latest_key() == 1

    # Concurrent writes against same base version without causal deps.
    e1 = a.push_event(
        entity_type="memo_card",
        entity_id="mc:persona.core",
        op="upsert",
        payload={"tone": "direct"},
        base_version=1,
    )
    e2 = b.push_event(
        entity_type="memo_card",
        entity_id="mc:persona.core",
        op="upsert",
        payload={"tone": "warm"},
        base_version=1,
    )

    ev_a = a.pull_events()
    ev_b = b.pull_events()
    merged = ev_a + ev_b
    # De-dup by event_id since each client can pull the same server stream.
    uniq = {e["event_id"]: e for e in merged}
    conflicts = detect_conflicts(list(uniq.values()))

    assert e1["event_id"] != e2["event_id"]
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["entity_type"] == "memo_card"
    assert c["entity_id"] == "mc:persona.core"
