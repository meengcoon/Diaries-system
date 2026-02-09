import importlib
import uuid


def _reload_privacy_gate(monkeypatch, tmp_path):
    salt_file = tmp_path / "salt.bin"
    monkeypatch.setenv("PRIVACY_SALT_HEX", "")
    monkeypatch.setenv("PRIVACY_SALT_FILE", str(salt_file))
    import pipeline.privacy_gate as pg
    return importlib.reload(pg)


def test_privacy_gate_redacts_and_uses_stable_hmac_ids(monkeypatch, tmp_path):
    pg = _reload_privacy_gate(monkeypatch, tmp_path)

    raw = (
        "我和张三今天在北京路见面，讨论了星海科技公司项目。"
        "邮箱是 test@example.com，手机是 13800138000，网站是 https://example.com。"
        "今天工作很累，但学习英语有进展。"
    )
    hints = {"PERSON": ["张三"], "ORG": ["星海科技公司"], "LOC": ["北京路"]}

    c1 = pg.build_cloud_contract_v1(raw_text=raw, ner_backend="lexicon", entity_hints=hints)
    c2 = pg.build_cloud_contract_v1(raw_text=raw, ner_backend="lexicon", entity_hints=hints)

    red = c1["text_redacted"]
    assert "test@example.com" not in red
    assert "13800138000" not in red
    assert "https://example.com" not in red
    assert "[EMAIL]" in red and "[PHONE]" in red and "[URL]" in red

    ents1 = {(e["type"], e["pseudo_id"]) for e in c1["entities"]}
    ents2 = {(e["type"], e["pseudo_id"]) for e in c2["entities"]}
    assert ents1 == ents2
    assert any(pid.startswith("P#") for _t, pid in ents1)
    assert any(pid.startswith("O#") for _t, pid in ents1)
    assert any(pid.startswith("L#") for _t, pid in ents1)

    # DATE pseudo ids should not be exported in v1.
    assert not any(e["type"] == "DATE" for e in c1["entities"])
    assert 3 <= len(c1["facts"]) <= 8
    assert str(uuid.UUID(c1["contract_id"])) == c1["contract_id"]

