from __future__ import annotations

import argparse
import os
import sys
from storage.db_core import connect  # 走统一 PRAGMA/timeout 封装
from typing import Optional

# Ensure project root is importable when running this script directly.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from retrieval.fts import fts_ready, rebuild_fts  # noqa: E402

try:
    from storage.db import get_db_path
except Exception:  # pragma: no cover
    from db import get_db_path  # type: ignore


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild SQLite FTS index (entry_fts) from entry_analysis")
    ap.add_argument("--limit", type=int, default=None, help="Rebuild at most N entries (default: all)")
    ap.add_argument("--clear", action="store_true", help="Clear entry_fts before rebuilding")
    args = ap.parse_args()

    if not fts_ready():
        print("FTS not ready: entry_fts table not found (SQLite may lack FTS5, or init_db not run).")
        return 2

    if args.clear:
        # Best-effort clear. Safe because rebuild uses delete+insert per row, but `--clear`
        # guarantees no stale rows remain if schema/prompt fields changed.
        try:
            conn = connect(get_db_path())
            conn.execute("DELETE FROM entry_fts;")
            conn.commit()
            conn.close()
            print("Cleared entry_fts")
        except Exception as e:
            print(f"FAIL: could not clear entry_fts: {e}")
            return 1

    res = rebuild_fts(limit=args.limit)
    if not isinstance(res, dict) or not res.get("ok"):
        print(f"FAIL: {res}")
        return 1

    print(f"PASS: rebuilt={res.get('rebuilt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())