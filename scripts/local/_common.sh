#!/usr/bin/env bash
# Shared helpers for Local-first orchestration. No secrets printed.
set -euo pipefail

LOCAL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$LOCAL_SCRIPT_DIR/../.." && pwd)"
UI_API_DIR="$REPO_ROOT/UI_API"
RUNTIME_DIR="${PROJECT_2026_RUNTIME_DIR:-$REPO_ROOT/runtime}"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"
STATE_DIR="$RUNTIME_DIR/state"
OBJ_DIR="$RUNTIME_DIR/object_storage"
TMP_DIR="$RUNTIME_DIR/tmp"

API_PID_FILE="$PID_DIR/api.pid"
WORKER_PID_FILE="$PID_DIR/worker.pid"
API_LOG="$LOG_DIR/api.log"
WORKER_LOG="$LOG_DIR/worker.log"

API_HOST="${APP_HOST:-127.0.0.1}"
API_PORT="${APP_PORT:-9000}"
ADMIN_PORT="${ADMIN_PORT:-9001}"
READY_URL="${READY_URL:-http://${API_HOST}:${API_PORT}/ready}"
LIVE_URL="${LIVE_URL:-http://${API_HOST}:${API_PORT}/live}"
READY_TIMEOUT_SEC="${READY_TIMEOUT_SEC:-45}"

ensure_runtime_dirs() {
  mkdir -p "$PID_DIR" "$LOG_DIR" "$STATE_DIR" "$OBJ_DIR" "$TMP_DIR"
}

is_pid_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' <"$file" || true
  fi
}

clear_stale_pid() {
  local file="$1"
  local name="$2"
  local pid
  pid="$(read_pid "$file")"
  if [[ -n "$pid" ]] && ! is_pid_running "$pid"; then
    echo "WARN: clearing stale $name pid $pid"
    rm -f "$file"
  fi
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE ":${port}\\s"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

python_bin() {
  if [[ -x "$UI_API_DIR/.venv/bin/python" ]]; then
    echo "$UI_API_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  else
    command -v python
  fi
}

wait_http_ok() {
  local url="$1"
  local timeout="${2:-$READY_TIMEOUT_SEC}"
  local start now
  start="$(date +%s)"
  while true; do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      if "$(python_bin)" - "$url" <<'PY' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2)
print("ok")
PY
      then
        return 0
      fi
    fi
    now="$(date +%s)"
    if (( now - start >= timeout )); then
      return 1
    fi
    sleep 0.5
  done
}

stop_pid_file() {
  local file="$1"
  local name="$2"
  local pid
  pid="$(read_pid "$file")"
  if [[ -z "$pid" ]]; then
    echo "$name: not running (no pid file)"
    return 0
  fi
  if ! is_pid_running "$pid"; then
    echo "$name: stale pid $pid removed"
    rm -f "$file"
    return 0
  fi
  echo "$name: stopping pid $pid"
  kill -TERM "$pid" 2>/dev/null || true
  local i
  for i in $(seq 1 20); do
    if ! is_pid_running "$pid"; then
      rm -f "$file"
      echo "$name: stopped"
      return 0
    fi
    sleep 0.25
  done
  echo "WARN: $name pid $pid still alive; sending KILL"
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$file"
}
