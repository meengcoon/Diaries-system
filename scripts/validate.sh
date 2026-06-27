#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

cd "$ROOT_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  printf 'Validation requires the project virtualenv at %s\n' "$PYTHON_BIN" >&2
  printf 'Create it with: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt\n' >&2
  exit 1
fi

export PATH="$ROOT_DIR/.venv/bin:$PATH"
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" -m pytest -q
"$PYTHON_BIN" -m compileall -q api services pipeline storage bot llm workers scripts server.py block_analyze.py
