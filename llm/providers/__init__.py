

# llm/providers/__init__.py
from __future__ import annotations

import os
from typing import Dict, Optional

from .base import BaseProvider, ProviderError, ProviderResult
from .deepseek_api import DeepSeekProvider
from .qwen_api import QwenProvider


def _try_get_settings_attr(key: str) -> Optional[str]:
    """Best-effort settings integration.

    If your project has core/settings.py exposing a `settings` object or module-level
    constants, this will pick them up without hard dependency.
    """
    try:
        from core import settings as core_settings  # type: ignore

        # Prefer a `settings` object (pydantic/dataclass style)
        if hasattr(core_settings, "settings"):
            s = getattr(core_settings, "settings")
            if hasattr(s, key):
                v = getattr(s, key)
                return str(v) if v is not None else None

        # Fall back to module-level attributes
        if hasattr(core_settings, key):
            v = getattr(core_settings, key)
            return str(v) if v is not None else None

    except Exception:
        return None

    return None


def _get_config(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read config from env first, then optional core.settings."""
    v = os.getenv(key)
    if v is not None and v != "":
        return v
    v2 = _try_get_settings_attr(key)
    if v2 is not None and v2 != "":
        return v2
    return default


# Optional: registry for inspection / extension
PROVIDERS = {
    "deepseek": DeepSeekProvider,
    "qwen": QwenProvider,
}


def get_provider(name: str) -> BaseProvider:
    """Create a configured provider instance by name.

    Supported:
      - deepseek: uses DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL (default https://api.deepseek.com)
      - qwen: uses DASHSCOPE_API_KEY, QWEN_BASE_URL (default https://dashscope-intl.aliyuncs.com/compatible-mode/v1)

    Raises:
      - ValueError: unknown provider name
      - ProviderError: missing API key (fatal)
    """
    n = (name or "").strip().lower()
    if n not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{name}'. Supported providers: {', '.join(sorted(PROVIDERS.keys()))}"
        )

    if n == "deepseek":
        api_key = _get_config("DEEPSEEK_API_KEY")
        base_url = _get_config("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if not api_key:
            raise ProviderError(
                code="missing_api_key",
                status=None,
                retryable=False,
                detail="DEEPSEEK_API_KEY is not set",
            )
        return DeepSeekProvider(api_key=api_key, base_url=base_url or "https://api.deepseek.com")

    if n == "qwen":
        api_key = _get_config("DASHSCOPE_API_KEY") or _get_config("QWEN_API_KEY")
        base_url = _get_config(
            "QWEN_BASE_URL",
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        if not api_key:
            raise ProviderError(
                code="missing_api_key",
                status=None,
                retryable=False,
                detail="DASHSCOPE_API_KEY (or QWEN_API_KEY) is not set",
            )
        return QwenProvider(
            api_key=api_key,
            base_url=base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )

    # Defensive fallback
    raise ValueError(
        f"Provider '{name}' is registered but not implemented in get_provider()."
    )


__all__ = [
    "BaseProvider",
    "ProviderError",
    "ProviderResult",
    "DeepSeekProvider",
    "QwenProvider",
    "PROVIDERS",
    "get_provider",
]