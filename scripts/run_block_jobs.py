#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Ensure project root is importable regardless of cwd/PYTHONPATH.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from workers.analysis_worker import _should_update_memory, main


if __name__ == "__main__":
    raise SystemExit(main())
