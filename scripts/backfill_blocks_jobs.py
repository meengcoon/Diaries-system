#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipeline.ingest import _filter_blocks_for_jobs  # type: ignore
from pipeline.segment import split_to_blocks
from storage import db


def _load_entries(limit: int) -> List[Dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, created_at, raw_text FROM entries ORDER BY id ASC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _delete_blocks_for_entry(entry_id: int) -> None:
    conn = db.connect()
    try:
        conn.execute("BEGIN;")
        conn.execute(
            "DELETE FROM block_jobs WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)",
            (int(entry_id),),
        )
        conn.execute(
            "DELETE FROM block_analysis WHERE block_id IN (SELECT block_id FROM entry_blocks WHERE entry_id=?)",
            (int(entry_id),),
        )
        conn.execute("DELETE FROM entry_blocks WHERE entry_id=?", (int(entry_id),))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill entry_blocks + block_jobs for existing entries")
    p.add_argument("--limit", type=int, default=100000)
    p.add_argument("--rebuild", action="store_true", help="delete existing blocks/jobs and rebuild")
    args = p.parse_args()

    db.init_db()
    entries = _load_entries(limit=max(1, int(args.limit)))

    scanned = len(entries)
    queued_entries = 0
    queued_blocks = 0
    skipped_existing = 0

    for e in entries:
        entry_id = int(e["id"])
        text = str(e.get("raw_text") or "").strip()
        created_at = str(e.get("created_at") or "")

        if not text:
            continue

        has_blocks = db.count_entry_blocks(entry_id) > 0
        if has_blocks and not args.rebuild:
            skipped_existing += 1
            continue

        if has_blocks and args.rebuild:
            _delete_blocks_for_entry(entry_id)

        blocks = _filter_blocks_for_jobs(split_to_blocks(text))
        if not blocks:
            continue

        now = created_at or db._utc_now_iso()
        for b in blocks:
            block_id = db.insert_entry_block(
                entry_id=entry_id,
                idx=int(b.get("idx", 0)),
                title=(b.get("title") or None),
                raw_text=str(b.get("raw_text") or b.get("text") or ""),
                created_at=created_at or now,
            )
            if block_id:
                db.insert_block_job(
                    block_id=int(block_id),
                    status="pending",
                    attempts=0,
                    last_error=None,
                    created_at=now,
                    updated_at=now,
                )
                queued_blocks += 1

        queued_entries += 1

    print(
        f"[DONE] scanned={scanned} queued_entries={queued_entries} "
        f"queued_blocks={queued_blocks} skipped_existing={skipped_existing} rebuild={bool(args.rebuild)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
