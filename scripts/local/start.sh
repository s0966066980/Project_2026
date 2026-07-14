#!/usr/bin/env bash
# Start API (+ optional Worker). Does not start Docker, Ollama, or Emotion.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

START_WORKER="${START_WORKER:-1}"
PROFILE="${APP_PROFILE:-local-dev}"
case "$PROFILE" in
  local-pilot)
    export APP_ENV="${APP_ENV:-production}"
    export MEMBER_STORAGE_BACKEND="${MEMBER_STORAGE_BACKEND:-postgres}"
    export SECURITY_ENFORCED="${SECURITY_ENFORCED:-true}"
    export ENABLE_DEMO_ROUTES=false
    export ENABLE_TEST_ROUTES=false
    export ENABLE_DEBUG_ROUTES=false
    export ALLOW_POSTGRES_JSON_FALLBACK=false
    export PAYMENT_BACKEND="${PAYMENT_BACKEND:-manual}"
    export POS_BACKEND="${POS_BACKEND:-manual}"
    export OBJECT_STORAGE_BACKEND="${OBJECT_STORAGE_BACKEND:-local}"
    READY_STRICT="${READY_STRICT:-1}"
    ;;
  local-postgres|local-full)
    export APP_ENV="${APP_ENV:-development}"
    export MEMBER_STORAGE_BACKEND="${MEMBER_STORAGE_BACKEND:-postgres}"
    export SECURITY_ENFORCED="${SECURITY_ENFORCED:-false}"
    READY_STRICT="${READY_STRICT:-1}"
    ;;
  *)
    export APP_ENV="${APP_ENV:-development}"
    export MEMBER_STORAGE_BACKEND="${MEMBER_STORAGE_BACKEND:-json}"
    export SECURITY_ENFORCED="${SECURITY_ENFORCED:-false}"
    READY_STRICT="${READY_STRICT:-0}"
    ;;
esac
ensure_runtime_dirs
clear_stale_pid "$API_PID_FILE" api
clear_stale_pid "$WORKER_PID_FILE" worker

PY="$(python_bin)"
if [[ ! -x "$PY" ]]; then
  echo "FAIL: python not found; run scripts/local/setup.sh" >&2
  exit 1
fi

api_pid="$(read_pid "$API_PID_FILE")"
if [[ -n "$api_pid" ]] && is_pid_running "$api_pid"; then
  echo "API already running (pid $api_pid)"
else
  if port_in_use "$API_PORT"; then
    echo "FAIL: port $API_PORT already in use by another process" >&2
    exit 1
  fi
  echo "Starting API on ${API_HOST}:${API_PORT} (APP_ENV=$APP_ENV storage=$MEMBER_STORAGE_BACKEND)"
  (
    cd "$UI_API_DIR"
    export PYTHONPATH="${UI_API_DIR}/backend:${UI_API_DIR}${PYTHONPATH:+:$PYTHONPATH}"
    export APP_ENV MEMBER_STORAGE_BACKEND SECURITY_ENFORCED
    nohup "$PY" main.py >>"$API_LOG" 2>&1 &
    echo $! >"$API_PID_FILE"
  )
fi

if [[ "$START_WORKER" == "1" ]]; then
  worker_pid="$(read_pid "$WORKER_PID_FILE")"
  if [[ -n "$worker_pid" ]] && is_pid_running "$worker_pid"; then
    echo "Worker already running (pid $worker_pid)"
  else
    echo "Starting Worker"
    (
      cd "$UI_API_DIR"
      export PYTHONPATH="${UI_API_DIR}/backend:${UI_API_DIR}${PYTHONPATH:+:$PYTHONPATH}"
      export APP_ENV MEMBER_STORAGE_BACKEND SECURITY_ENFORCED
      nohup "$PY" backend/scripts/run_worker.py >>"$WORKER_LOG" 2>&1 &
      echo $! >"$WORKER_PID_FILE"
    )
  fi
else
  echo "Worker: skipped (START_WORKER=0)"
fi

probe_url="$LIVE_URL"
if [[ "$READY_STRICT" == "1" || "$MEMBER_STORAGE_BACKEND" == "postgres" ]]; then
  probe_url="$READY_URL"
fi
echo "Waiting for: $probe_url"
if wait_http_ok "$probe_url" "$READY_TIMEOUT_SEC"; then
  echo "start: OK"
  echo "  Kiosk: http://${API_HOST}:${API_PORT}/kiosk"
  echo "  Admin: http://${API_HOST}:${ADMIN_PORT}/admin"
  echo "  live:  $LIVE_URL"
  echo "  ready: $READY_URL"
  echo "  logs:  $LOG_DIR"
  exit 0
fi

echo "FAIL: API did not become available within ${READY_TIMEOUT_SEC}s" >&2
echo "  See $API_LOG" >&2
exit 1
