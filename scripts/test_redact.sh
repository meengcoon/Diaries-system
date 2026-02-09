#!/usr/bin/env bash
set -euo pipefail

FILE="${1:-diaries/tmp_diary.txt}"
MAX_CHARS="${2:-800}"

echo "== Input =="
echo "file: $FILE"
echo "max_chars: $MAX_CHARS"
echo

PYTHONPATH=. python - <<'PY'
import os, json, sys
from pipeline.segment import split_to_blocks
from utils.redact import redact_text  # 你写的 redact 入口函数名如果不同，改这里

file_path = os.environ.get("FILE_PATH") or sys.argv[0]  # dummy
PY
PYTHONPATH=. python - <<PY
import json
from pipeline.segment import split_to_blocks
from utils.redact import redact_text  # 若你函数名不是 redact_text，请改成你的入口

path = r"$FILE"
max_chars = int(r"$MAX_CHARS")

t = open(path, "r", encoding="utf-8").read()
blocks = split_to_blocks(t, max_chars=max_chars)

print(f"Total blocks: {len(blocks)}")
print()

cloud_payload = []
for b in blocks:
    idx = b["idx"]
    text = b["text"]
    is_sensitive = bool(b.get("is_sensitive"))

    if is_sensitive:
        print(f"[SKIP] idx={idx} sensitive=True len={len(text)}")
        continue

    red = redact_text(text, placeholder="__")
    changed = (red != text)
    cloud_payload.append({"idx": idx, "text": red})

    print(f"[SEND] idx={idx} sensitive=False len={len(text)} changed={changed}")
    if changed:
        # 只展示前 120 字，避免刷屏
        print("  before:", text[:120].replace("\\n","\\n"))
        print("  after :", red[:120].replace("\\n","\\n"))

print()
print("== Cloud payload preview (first 2) ==")
print(json.dumps(cloud_payload[:2], ensure_ascii=False, indent=2))

# 强校验：确保 payload 里不包含 '[' 或 ']'（如果你允许普通方括号存在，这条会误报，可删）
import re

bad = []
for item in cloud_payload:
    txt = item["text"]
    # 你选择用 [] 作为显式标记，所以云端 payload 中任何残留的 '[' 或 ']' 都视为泄露
    if re.search(r"[\[\]]", txt):
        bad.append(item["idx"])
if bad:
    print(f"WARNING: some sent blocks still contain brackets: {bad}")
else:
    print("OK: no brackets remain in sent blocks (all redacted).")
PY