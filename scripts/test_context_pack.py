

from __future__ import annotations

import argparse
import os
import sys
# Ensure project root is importable when running this script directly.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
from typing import Any, Dict, List

from pipeline.context_pack import (
    build_context_pack,
    build_context_pack_debug_text,
    build_context_pack_text,
)


def _ids(pack: Dict[str, Any]) -> List[int]:
    return [int(x["entry_id"]) for x in (pack.get("topk") or []) if isinstance(x, dict) and "entry_id" in x]


def main() -> int:
    p = argparse.ArgumentParser(description="M3: context_pack smoke/acceptance test")
    p.add_argument("--q", "--query", dest="query", required=True, help="search query")
    p.add_argument("--top-k", dest="top_k", type=int, default=6)
    p.add_argument("--recent-n", dest="recent_n", type=int, default=8)
    p.add_argument("--budget", dest="budget", type=int, default=5000, help="char budget for model payload")
    p.add_argument("--repeat", dest="repeat", type=int, default=2, help="run twice to verify stability")
    p.add_argument("--dump", dest="dump", action="store_true", help="print model payload JSON")
    p.add_argument("--dump-debug", dest="dump_debug", action="store_true", help="print full pack including meta")
    args = p.parse_args()

    packs: List[Dict[str, Any]] = []
    texts: List[str] = []

    for i in range(max(1, args.repeat)):
        pack = build_context_pack(
            args.query,
            top_k=args.top_k,
            recent_n=args.recent_n,
            char_budget=args.budget,
        )
        text = build_context_pack_text(pack)

        packs.append(pack)
        texts.append(text)

        meta = pack.get("meta") or {}
        print(f"run={i+1}")
        print(f"  initial_counts={meta.get('initial_counts')} initial_chars_model={meta.get('initial_chars')}")
        print(f"  final_chars_model={meta.get('final_chars_model')} final_chars_total={meta.get('final_chars_total')}")
        print(f"  text_len={len(text)}")
        print(f"  topk_ids={_ids(pack)}")
        print(f"  mem_cards={[c.get('card_id') for c in (pack.get('mem_cards') or []) if isinstance(c, dict)]}")
        print(f"  steps={meta.get('steps')}")

        # Hard assertions for M3
        if len(text) > int(args.budget):
            raise SystemExit(f"FAIL: model payload text_len {len(text)} exceeds budget {args.budget}")

    # Stability check: same query should yield same ordering in the same DB state.
    if len(packs) >= 2:
        if _ids(packs[0]) != _ids(packs[1]):
            raise SystemExit(f"FAIL: topk ordering unstable: {_ids(packs[0])} != {_ids(packs[1])}")
        if texts[0] != texts[1]:
            # Minor fields like created_at may differ; this checks only payload text.
            # If you want deterministic created_at, set it outside build_context_pack.
            print("WARN: payload text differs between runs (expected if created_at changes).")

    if args.dump:
        print(texts[-1])

    if args.dump_debug:
        print(build_context_pack_debug_text(packs[-1]))

    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())