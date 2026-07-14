#!/usr/bin/env bash
# Show local process / port status. Exit 0 if API up, 1 otherwise.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

ensure_runtime_dirs
clear_stale_pid "$API_PID_FILE" api
clear_stale_pid "$WORKER_PID_FILE" worker

api_pid="$(read_pid "$API_PID_FILE")"
worker_pid="$(read_pid "$WORKER_PID_FILE")"
api_ok=0
worker_ok=0

if [[ -n "$api_pid" ]] && is_pid_running "$api_pid"; then
  echo "API: running pid=$api_pid"
  api_ok=1
else
  echo "API: stopped"
fi
if [[ -n "$worker_pid" ]] && is_pid_running "$worker_pid"; then
  echo "Worker: running pid=$worker_pid"
  worker_ok=1
else
  echo "Worker: stopped"
fi

if port_in_use "$API_PORT"; then
  echo "Port ${API_PORT}: LISTEN"
else
  echo "Port ${API_PORT}: free"
fi

if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 2 "$LIVE_URL" >/dev/null 2>&1; then
    echo "live: OK"
  else
    echo "live: FAIL"
  fi
  if curl -fsS --max-time 2 "$READY_URL" >/dev/null 2>&1; then
    echo "ready: OK"
  else
    echo "ready: FAIL"
  fi
fi

echo "logs: $LOG_DIR"
if [[ "$api_ok" -eq 1 ]]; then
  exit 0
fi
exit 1
