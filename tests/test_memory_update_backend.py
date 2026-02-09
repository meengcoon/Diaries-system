from pipeline import memory_update as mu


def test_mem_update_uses_cloud_when_cloud_enabled(monkeypatch):
    monkeypatch.delenv("MEM_UPDATE_FORCE_LOCAL", raising=False)
    monkeypatch.delenv("MEM_UPDATE_FORCE_CLOUD", raising=False)
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    assert mu._should_use_cloud_mem_update() is True


def test_mem_update_force_local_overrides_cloud(monkeypatch):
    monkeypatch.setenv("MEM_UPDATE_FORCE_LOCAL", "1")
    monkeypatch.setenv("MEM_UPDATE_FORCE_CLOUD", "1")
    monkeypatch.setenv("CLOUD_ENABLED", "1")
    assert mu._should_use_cloud_mem_update() is False


def test_mem_update_local_llm_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MEM_UPDATE_USE_LOCAL_LLM", raising=False)
    assert mu._should_use_local_mem_llm() is False
