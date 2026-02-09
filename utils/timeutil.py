# utils/timeutil.py
from __future__ import annotations

from datetime import datetime, timezone

def utc_now_iso(*, timespec: str = "seconds") -> str:
    """UTC, timezone-aware ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec=timespec)

def local_today_str() -> str:
    """Local date string YYYY-MM-DD (uses system local timezone)."""
    return datetime.now().astimezone().strftime("%Y-%m-%d")
