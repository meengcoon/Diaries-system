from bot import generation_router as gr


def _base_payload():
    return {
        "intent": "weekly_review",
        "prompt_version": "v1",
        "is_idle": True,
        "local_model": "local",
    }


def test_route_blocks_when_privacy_level_exceeds_limit(monkeypatch):
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    monkeypatch.setenv("CLOUD_MAX_PRIVACY_LEVEL", "L1")
    p = _base_payload()
    p["privacy_level"] = "L2"

    d = gr.route("chat_answer", p)
    assert d.backend == "local"
    assert "privacy_blocked" in d.reason


def test_route_blocks_raw_text_upload(monkeypatch):
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    monkeypatch.setenv("BLOCK_RAW_TEXT_UPLOAD", "1")
    p = _base_payload()
    p["force_cloud"] = True
    p["raw_text"] = "secret raw text"

    d = gr.route("chat_answer", p)
    assert d.backend == "local"
    assert d.reason == "raw_text_upload_blocked"


def test_route_blocks_cloud_training_when_disabled(monkeypatch):
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    monkeypatch.setenv("ALLOW_CLOUD_TRAINING", "0")
    p = _base_payload()
    p["force_cloud"] = True
    p["use_for_training"] = True
    p["privacy_level"] = "L2"

    d = gr.route("chat_answer", p)
    assert d.backend == "local"
    assert d.reason == "cloud_training_disabled"


def test_route_allows_cloud_when_policy_satisfied(monkeypatch):
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    monkeypatch.setenv("ALLOW_CLOUD_INFERENCE", "1")
    monkeypatch.setenv("CLOUD_MAX_PRIVACY_LEVEL", "L2")
    monkeypatch.setenv("CLOUD_CHAR_THRESHOLD", "1")
    p = _base_payload()
    p["privacy_level"] = "L1"
    p["messages"] = [{"role": "user", "content": "hi"}]

    d = gr.route("chat_answer", p)
    assert d.backend == "cloud"


def test_sanitize_cloud_messages_masks_pii():
    msgs = [
        {"role": "user", "content": "mail me at a@b.com and call 13800138000 https://x.y"},
    ]
    out = gr._sanitize_cloud_messages(msgs)
    s = out[0]["content"]
    assert "a@b.com" not in s
    assert "13800138000" not in s
    assert "https://x.y" not in s
