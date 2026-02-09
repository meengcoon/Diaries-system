from sync.client import LocalSyncService, SyncClient


def test_key_rotation_and_revocation(tmp_path):
    svc = LocalSyncService(str(tmp_path / "sync_rotate.sqlite3"))

    a = SyncClient(service=svc, device_id="dev_a")
    b = SyncClient(service=svc, device_id="dev_b")

    # Bootstrap v1 and grant B.
    assert a.bootstrap_group() == 1
    a.share_key_with_device(target_device_id="dev_b", target_public_key_b64=b.keys.public_key_b64)
    assert b.fetch_latest_key() == 1

    # v1 event is readable by both.
    a.push_event(
        entity_type="memo_card",
        entity_id="mc:test",
        op="upsert",
        payload={"v": 1},
    )
    got_b_v1 = b.pull_events()
    assert any(e.get("payload", {}).get("v") == 1 for e in got_b_v1)

    # Revoke B and rotate to v2 (only active devices get envelope).
    svc.revoke_device(device_id="dev_b")
    assert a.rotate_group_key() == 2

    # A writes v2 event.
    a.push_event(
        entity_type="memo_card",
        entity_id="mc:test",
        op="upsert",
        payload={"v": 2},
    )

    # B can still fetch stream, but cannot decrypt v2 due to missing key envelope.
    got_b_after = b.pull_events()
    assert not any(e.get("group_key_version") == 2 for e in got_b_after)
    assert not any(e.get("payload", {}).get("v") == 2 for e in got_b_after)

    # A can decrypt v2.
    got_a_after = a.pull_events()
    assert any(e.get("payload", {}).get("v") == 2 for e in got_a_after)
