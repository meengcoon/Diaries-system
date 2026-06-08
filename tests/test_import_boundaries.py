from __future__ import annotations

import subprocess
import sys


def test_core_api_imports_do_not_load_audio_analysis_stack():
    code = """
import sys
import api.routes_diary
import server
loaded = set(sys.modules)
for name in ("pipeline.audio_features", "services.audio_ingest_service", "numpy"):
    if name in loaded:
        raise SystemExit(f"unexpected import: {name}")
print("ok")
"""
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr or res.stdout
