#!/usr/bin/env bash
# Stop only processes started by scripts/local/start.sh (pid files).
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

ensure_runtime_dirs
stop_pid_file "$WORKER_PID_FILE" worker
stop_pid_file "$API_PID_FILE" api
echo "stop: done"
