# core/settings.py
from __future__ import annotations


import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    if not v:
        return default
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = (os.getenv(name) or "").strip()
    if not v:
        return default
    try:
        return float(v)
    except Exception:
        return default


# -------------------------
# Cloud LLM (optional)
# Default: completely disabled unless CLOUD_ENABLED=1.
# -------------------------
CLOUD_ENABLED: bool = _env_bool("CLOUD_ENABLED", False)
CLOUD_ONLY_WHEN_IDLE: bool = _env_bool("CLOUD_ONLY_WHEN_IDLE", False)
CLOUD_DEFAULT_PROVIDER: str = os.getenv("CLOUD_DEFAULT_PROVIDER", "deepseek")

# Routing thresholds / safety
CLOUD_CHAR_THRESHOLD: int = _env_int("CLOUD_CHAR_THRESHOLD", 6000)
CLOUD_FAIL_WINDOW_S: int = _env_int("CLOUD_FAIL_WINDOW_S", 600)
CLOUD_FAIL_THRESHOLD: int = _env_int("CLOUD_FAIL_THRESHOLD", 3)

# Cloud call behavior
CLOUD_RETRIES: int = _env_int("CLOUD_RETRIES", 2)
CLOUD_TIMEOUT_CONNECT_S: float = _env_float("CLOUD_TIMEOUT_CONNECT_S", 10.0)
CLOUD_TIMEOUT_READ_S: float = _env_float("CLOUD_TIMEOUT_READ_S", 120.0)

# Cache (for cloud responses). Can be disabled for debugging.
LLM_CACHE_ENABLED: bool = _env_bool("LLM_CACHE_ENABLED", True)
LLM_CACHE_TTL_S: int = _env_int("LLM_CACHE_TTL_S", 0)

# Provider credentials / endpoints (leave blank by default; never required unless cloud is enabled).
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
QWEN_CLOUD_MODEL: str = os.getenv("QWEN_CLOUD_MODEL", "qwen-plus")

# Models
PHI_MODEL: str = os.getenv("PHI_MODEL", "phi3.5:3.8b")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "qwen2.5:7b")

# Prompt versions (version everything; keep defaults stable)
PROMPT_VERSION_BLOCK: str = os.getenv("PROMPT_VERSION_BLOCK", "phi_block_extract_v1")
PROMPT_VERSION_ENTRY: str = os.getenv("PROMPT_VERSION_ENTRY", "phi_extract_v1")
PROMPT_VERSION_MEM_UPDATE: str = os.getenv("PROMPT_VERSION_MEM_UPDATE", "phi_mem_update_v1")

# Generation limits
PHI_NUM_PREDICT: int = int(os.getenv("PHI_NUM_PREDICT", "350"))

# Block sizing / filtering (shared by segmenter and analyzer)
MIN_BLOCK_CHARS: int = int(os.getenv("MIN_BLOCK_CHARS", "80"))
TARGET_BLOCK_CHARS: int = int(os.getenv("TARGET_BLOCK_CHARS", "3200"))
MAX_BLOCK_CHARS: int = int(os.getenv("MAX_BLOCK_CHARS", "6000"))

# Memory update model (defaults to PHI_MODEL)
MEM_UPDATE_MODEL: str = os.getenv("MEM_UPDATE_MODEL", PHI_MODEL)

# Privacy gate (local-only redaction/pseudonymization)
PRIVACY_NER_BACKEND: str = (os.getenv("PRIVACY_NER_BACKEND", "none") or "none").strip().lower()
PRIVACY_SALT_HEX: str = (os.getenv("PRIVACY_SALT_HEX", "") or "").strip()
PRIVACY_SALT_FILE: str = (
    os.getenv("PRIVACY_SALT_FILE")
    or str(Path.home() / ".diary_system" / "privacy_salt.bin")
).strip()
