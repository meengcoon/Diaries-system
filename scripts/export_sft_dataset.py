#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from storage.db_core import connect


SYSTEM_ZH = (
    "你是一个中文日记助理。\n"
    "你只能基于给定上下文回答，不要编造。\n"
    "若上下文没有证据，请回答：未记录。"
)


def _safe_json_loads(s: str) -> Any:
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def _build_context(analysis: Dict[str, Any]) -> str:
    summary = str(analysis.get("summary_1_3") or "").strip()
    topics = analysis.get("topics") or []
    facts = analysis.get("facts") or []
    todos = analysis.get("todos") or []

    out = []
    if summary:
        out.append(f"summary: {summary}")
    if topics:
        out.append("topics: " + " | ".join(str(x) for x in topics[:8]))
    if facts:
        out.append("facts: " + " | ".join(str(x) for x in facts[:10]))
    if todos:
        out.append("todos: " + " | ".join(str(x) for x in todos[:8]))
    return "\n".join(out)


def _mk_record(*, instruction: str, context: str, output: str) -> Dict[str, Any]:
    user = f"任务: {instruction}\n\nCONTEXT:\n{context}".strip()
    return {
        "system": SYSTEM_ZH,
        "instruction": instruction,
        "input": context,
        "output": output,
        "messages": [
            {"role": "system", "content": SYSTEM_ZH},
            {"role": "user", "content": user},
            {"role": "assistant", "content": output},
        ],
    }


def _extract_traits(summary: str, topics: List[str]) -> str:
    summary = (summary or "").strip()
    if not summary:
        return "未记录"
    toks = [t for t in topics if isinstance(t, str) and t.strip()]
    if toks:
        return f"从记录看，你常关注：{'、'.join(toks[:4])}。你近期状态：{summary}"
    return f"从记录看，你近期状态：{summary}"


def export_dataset(limit: int, seed: int) -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT e.id AS entry_id, e.raw_text, a.analysis_json
            FROM entries e
            JOIN entry_analysis a ON a.entry_id = e.id
            ORDER BY e.id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        conn.close()

    rng = random.Random(seed)
    out: List[Dict[str, Any]] = []

    for r in rows:
        analysis = _safe_json_loads(r["analysis_json"]) or {}
        if not isinstance(analysis, dict):
            continue

        context = _build_context(analysis)
        if not context:
            continue

        summary = str(analysis.get("summary_1_3") or "").strip()
        facts = [str(x).strip() for x in (analysis.get("facts") or []) if str(x).strip()]
        topics = [str(x).strip() for x in (analysis.get("topics") or []) if str(x).strip()]
        todos = [str(x).strip() for x in (analysis.get("todos") or []) if str(x).strip()]

        # Task A: summary
        out.append(
            _mk_record(
                instruction="请根据上下文，给出1-2句简短总结。",
                context=context,
                output=summary or "未记录",
            )
        )

        # Task B: key facts
        out.append(
            _mk_record(
                instruction="列出最多3条关键信息，缺失则回答未记录。",
                context=context,
                output=("；".join(facts[:3]) if facts else "未记录"),
            )
        )

        # Task C: todo extraction
        out.append(
            _mk_record(
                instruction="提取待办事项（最多3条），没有就回答未记录。",
                context=context,
                output=("；".join(todos[:3]) if todos else "未记录"),
            )
        )

        # Task D: persona-style statement
        out.append(
            _mk_record(
                instruction="基于上下文，说一下这个人的近况和特点（不要编造）。",
                context=context,
                output=_extract_traits(summary, topics),
            )
        )

        # Optional negative sample: ask unrelated question -> 未记录
        if rng.random() < 0.3:
            out.append(
                _mk_record(
                    instruction="这个人小时候住在哪？",
                    context=context,
                    output="未记录",
                )
            )

    return out


def write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def split_train_val(items: List[Dict[str, Any]], val_ratio: float, seed: int) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    idx = list(range(len(items)))
    rng = random.Random(seed)
    rng.shuffle(idx)
    n_val = max(1, int(len(items) * val_ratio)) if items else 0
    val_idx = set(idx[:n_val])
    train = [items[i] for i in range(len(items)) if i not in val_idx]
    val = [items[i] for i in range(len(items)) if i in val_idx]
    return train, val


def main() -> int:
    p = argparse.ArgumentParser(description="Export SFT dataset from diary SQLite")
    p.add_argument("--limit", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--val-ratio", type=float, default=0.1)
    p.add_argument("--out-dir", default="training_data")
    args = p.parse_args()

    items = export_dataset(limit=max(1, int(args.limit)), seed=int(args.seed))
    train, val = split_train_val(items, val_ratio=float(args.val_ratio), seed=int(args.seed))

    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "sft_train.jsonl", train)
    write_jsonl(out_dir / "sft_val.jsonl", val)

    print(
        json.dumps(
            {
                "ok": True,
                "total": len(items),
                "train": len(train),
                "val": len(val),
                "out_dir": str(out_dir.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
