from persona.policy_store import get_active_policy, list_policies, save_policy
from storage import db


def test_persona_policy_versioning(monkeypatch, tmp_path):
    db_path = tmp_path / "policy.sqlite3"
    monkeypatch.setenv("DIARY_DB_PATH", str(db_path))
    db.init_db()

    v1 = save_policy({"style": "direct", "lang": "zh"}, activate=True)
    v2 = save_policy({"style": "warm", "lang": "zh"}, activate=True)

    assert v2 > v1
    active = get_active_policy()
    assert active is not None
    assert active["version"] == v2
    assert active["profile"]["style"] == "warm"

    rows = list_policies(limit=10)
    assert len(rows) >= 2
