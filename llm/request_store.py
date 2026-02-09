from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional


_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|token|secret|password|passwd|access[_-]?key)",
    re.IGNORECASE,
)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _stable_json_dumps(obj: Any) -> str:
    """Deterministic JSON serialization.

    - sort_keys ensures dict key order does not affect output.
    - separators removes whitespace that could affect hashing.
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _redact_sensitive(obj: Any) -> Any:
    """Recursively redact sensitive values.

    This is a defensive guard: we do *not* want any API keys / tokens to be
    written to disk or database.
    """
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            if _SENSITIVE_KEY_RE.search(str(k) or ""):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact_sensitive(v)
        return out
    if isinstance(obj, list):
        return [_redact_sensitive(x) for x in obj]
    if isinstance(obj, tuple):
        return [_redact_sensitive(x) for x in obj]
    return obj


def hash_request(
    *,
    provider: str,
    model: str,
    messages: list[dict],
    params: Optional[Mapping[str, Any]] = None,
    prompt_version: Optional[str] = None,
) -> str:
    """Compute a stable request hash.

    Requirements:
      - Field ordering must not affect the hash.
      - Sensitive fields must not influence or leak via hashing payload.

    Note:
      - messages order *does* affect the hash (intentionally).
    """
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "messages": messages,
        "params": dict(params) if params else {},
    }
    payload = _redact_sensitive(payload)
    s = _stable_json_dumps(payload)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _default_store_root() -> Path:
    """Best-effort default location.

    Prefer explicit env var, otherwise fall back to a sensible per-user directory.
    - macOS: ~/Library/Application Support/DiarySystem
    - others: ~/.diary_system

    Callers may ignore this and pass their own data_dir.
    """
    env = os.getenv("DIARY_DATA_DIR")
    if env:
        return Path(env).expanduser()

    home = Path.home()
    # Heuristic for macOS
    mac_root = home / "Library" / "Application Support" / "DiarySystem"
    if (home / "Library").exists() and (home / "Library" / "Application Support").exists():
        return mac_root

    return home / ".diary_system"


def _call_dir(data_dir: Optional[Path], request_hash: str) -> Path:
    root = (data_dir or _default_store_root()).expanduser()
    # Keep everything under a single, greppable folder.
    return root / "requests" / request_hash


def store_request(
    request_hash: str,
    payload_json: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    """Persist the request payload as JSON (redacted).

    Returns the path written.
    """
    p = _call_dir(data_dir, request_hash) / "request.json"
    safe = _redact_sensitive(dict(payload_json))
    _atomic_write_text(p, json.dumps(safe, ensure_ascii=False, indent=2))
    return p


def store_response(
    request_hash: str,
    payload_json: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    """Persist the response payload as JSON (redacted)."""
    p = _call_dir(data_dir, request_hash) / "response.json"
    safe = _redact_sensitive(dict(payload_json))
    _atomic_write_text(p, json.dumps(safe, ensure_ascii=False, indent=2))
    return p


def store_meta(
    request_hash: str,
    meta_json: Mapping[str, Any],
    *,
    data_dir: Optional[Path] = None,
) -> Path:
    """Persist meta/audit info for a call (timestamps, ms, cache_hit, etc.)."""
    p = _call_dir(data_dir, request_hash) / "meta.json"
    safe = _redact_sensitive(dict(meta_json))
    _atomic_write_text(p, json.dumps(safe, ensure_ascii=False, indent=2))
    return p


# ---------------------------------------------------------------------------
# Backward-compatible helper (your earlier quick draft).
# Keep it so existing call sites don't break.
# ---------------------------------------------------------------------------

def save_request_json(data_dir: Path, *, provider: str, task: str, payload: dict) -> Path:
    """Legacy helper: write a timestamped request payload.

    Prefer hash_request + store_request/store_response for stable caching & replay.
    """
    req_dir = data_dir / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    ts = _utc_ts()
    path = req_dir / f"{ts}_{provider}_{task}.json"
    safe = _redact_sensitive(payload)
    _atomic_write_text(path, json.dumps(safe, ensure_ascii=False, indent=2))
    return path
