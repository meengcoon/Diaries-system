#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"
SINGLE_UI_HOST="${SINGLE_UI_HOST:-127.0.0.1}"
SINGLE_UI_PORT="${SINGLE_UI_PORT:-8000}"
SINGLE_UI_BROWSER="${SINGLE_UI_BROWSER:-default}" # default|safari|chrome
SINGLE_UI_KILL_OLD="${SINGLE_UI_KILL_OLD:-0}"     # 1 => kill existing listener on port
URL="http://${SINGLE_UI_HOST}:${SINGLE_UI_PORT}/?single_ui=1"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[ERROR] .env not found: $ENV_FILE"
  exit 1
fi

if lsof -nP -iTCP:"$SINGLE_UI_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[WARN] Port ${SINGLE_UI_PORT} is already in use."
  lsof -nP -iTCP:"$SINGLE_UI_PORT" -sTCP:LISTEN
  if [[ "$SINGLE_UI_KILL_OLD" == "1" ]]; then
    pids="$(lsof -t -nP -iTCP:"$SINGLE_UI_PORT" -sTCP:LISTEN | tr '\n' ' ')"
    if [[ -n "${pids// }" ]]; then
      echo "[INFO] Killing old listener(s): $pids"
      kill $pids || true
      sleep 1
    fi
  else
    echo "[ERROR] Start aborted. Re-run with SINGLE_UI_KILL_OLD=1 to auto-kill old listener."
    echo "        Example: SINGLE_UI_KILL_OLD=1 scripts/start_single_ui.sh"
    exit 1
  fi
fi

# Export all vars from .env
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Force a single canonical origin so Safari/Chrome hit the same UI.
export HOST="$SINGLE_UI_HOST"
export PORT="$SINGLE_UI_PORT"
# Keep single-ui startup deterministic: disable uvicorn reloader unless explicitly set.
export UVICORN_RELOAD="${UVICORN_RELOAD:-0}"

pick_python() {
  local cand
  local cands=()
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    cands+=("${VIRTUAL_ENV}/bin/python")
  fi
  if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    cands+=("$ROOT_DIR/.venv/bin/python")
  fi
  if [[ -n "$PYTHON_BIN" ]]; then
    cands+=("$PYTHON_BIN")
  fi
  cands+=("python" "python3" "/usr/bin/python3")

  for cand in "${cands[@]}"; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" --version >/dev/null 2>&1 && "$cand" -c "import fastapi" >/dev/null 2>&1; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

if ! RUN_PY="$(pick_python)"; then
  echo "[ERROR] No suitable Python interpreter found (requires fastapi)."
  echo "        Tried: ${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/python, }$ROOT_DIR/.venv/bin/python, ${PYTHON_BIN:+$PYTHON_BIN, }python, python3, /usr/bin/python3"
  echo "        Hint: activate your venv, or install deps into the interpreter you want to use."
  exit 1
fi
echo "[INFO] Python: $RUN_PY ($($RUN_PY --version 2>&1))"

SERVER_LOG="$ROOT_DIR/.single_ui_server.log"
: > "$SERVER_LOG"
"$RUN_PY" "$ROOT_DIR/server.py" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[INFO] Waiting for server: $URL"
for _ in $(seq 1 60); do
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID" || rc=$?
    rc="${rc:-1}"
    if [[ "$rc" -gt 128 ]]; then
      sig=$((rc - 128))
      echo "[ERROR] Server exited during startup (rc=$rc, signal=$sig)."
    else
      echo "[ERROR] Server exited during startup (rc=$rc)."
    fi
    echo "[ERROR] Last server logs:"
    tail -n 80 "$SERVER_LOG" || true
    exit 1
  fi
  if curl -fsS "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "$URL" >/dev/null 2>&1; then
  echo "[ERROR] Server did not become ready in time: $URL"
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    echo "[ERROR] Server is still running; check logs: $SERVER_LOG"
  else
    wait "$SERVER_PID" || rc=$?
    rc="${rc:-1}"
    echo "[ERROR] Server exited before readiness (rc=$rc)."
  fi
  tail -n 80 "$SERVER_LOG" || true
  exit 1
fi

case "$SINGLE_UI_BROWSER" in
  safari)
    open -a Safari "$URL"
    ;;
  chrome)
    open -a "Google Chrome" "$URL"
    ;;
  *)
    open "$URL"
    ;;
esac

echo "[INFO] Opened: $URL"
echo "[INFO] Browser mode: $SINGLE_UI_BROWSER"
echo "[INFO] Keep this terminal running. Press Ctrl+C to stop."
echo "[INFO] Server log: $SERVER_LOG"

wait "$SERVER_PID"
