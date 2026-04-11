from __future__ import annotations

from core.settings import env_str

def analysis_primary_backend() -> str:
    raw = env_str("ANALYZE_PRIMARY_BACKEND", "cloud").strip().lower()
    if raw in {"local", "cloud"}:
        return raw
    return "cloud"


def normalize_provider(preferred_provider: str, *, default: str = "deepseek") -> str:
    provider = (preferred_provider or default).strip().lower()
    if provider not in {"deepseek", "qwen"}:
        return default
    return provider
