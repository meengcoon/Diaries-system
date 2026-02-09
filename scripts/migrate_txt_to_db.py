from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import re
import sys

# 让脚本在 `python scripts/migrate_txt_to_db.py` 方式运行时也能 import 项目根目录下的模块
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 优先使用 storage.db；如果你将来改成根目录 db.py，也兼容
try:
    from storage.db import init_db, insert_entry  # type: ignore
except Exception:
    from db import init_db, insert_entry  # type: ignore


def parse_date_from_filename(name: str) -> datetime | None:
    """
    支持：
      - 2025-12-20.txt
      - 2025-12-20_10-30-00.txt
    """
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:_(\d{2}-\d{2}-\d{2}))?\.txt$", name)
    if not m:
        return None
    date_part = m.group(1)
    time_part = m.group(2)
    if time_part:
        return datetime.fromisoformat(f"{date_part}T{time_part.replace('-', ':')}")
    return datetime.fromisoformat(f"{date_part}T00:00:00")


def main() -> int:
    diaries_dir = BASE_DIR / "diaries"
    if not diaries_dir.exists():
        print(f"[ERR] diaries dir not found: {diaries_dir}")
        return 1

    init_db()

    files = sorted(diaries_dir.glob("*.txt"))
    if not files:
        print("[OK] no txt files to migrate.")
        return 0

    imported = 0
    skipped_empty = 0
    failed = 0

    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8").strip()
            if not text:
                skipped_empty += 1
                continue

            dt = parse_date_from_filename(fp.name)
            if dt is None:
                # fallback：用文件 mtime
                mtime = fp.stat().st_mtime
                dt = datetime.fromtimestamp(mtime, tz=timezone.utc).replace(tzinfo=None)

            created_at = dt.isoformat(timespec="seconds")
            entry_id = insert_entry(raw_text=text, created_at=created_at, source=f"migrate:{fp.name}")

            # insert_entry 若遇到重复可能返回已有 id 或 -1（取决于你的实现）
            if isinstance(entry_id, int) and entry_id > 0:
                imported += 1
        except Exception as e:
            failed += 1
            print(f"[ERR] {fp.name}: {e}")

    print(f"[DONE] scanned={len(files)}, imported~={imported}, empty={skipped_empty}, failed={failed}")
    print("Tip: re-run is safe if your DB uses sha256 UNIQUE + INSERT OR IGNORE.")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())