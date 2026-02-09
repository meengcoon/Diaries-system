#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] .env not found: $ENV_FILE"
  echo "Copy $ROOT_DIR/.env.example to $ROOT_DIR/.env and fill keys."
  exit 1
fi

# Export all vars from .env into current shell
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

python3 "$ROOT_DIR/server.py"
