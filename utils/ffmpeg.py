from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_ffmpeg() -> str | None:
    direct = shutil.which("ffmpeg")
    if direct:
        return direct

    candidates = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]

    for cand in candidates:
        if Path(cand).exists():
            return cand

    extra = (os.getenv("FFMPEG_BIN") or "").strip()
    if extra and Path(extra).exists():
        return extra

    return None
