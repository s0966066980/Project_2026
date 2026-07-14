#!/usr/bin/env bash
# Fast local gate: static + smoke/core subset. No Docker, no full 300+ suite.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

PY="$(python_bin)"
cd "$UI_API_DIR"
export PYTHONPATH="${UI_API_DIR}/backend:${UI_API_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export APP_ENV="${APP_ENV:-test}"
export MEMBER_STORAGE_BACKEND=json
export DATABASE_URL=
export TEST_DATA_DIR="${TEST_DATA_DIR:-$RUNTIME_DIR/tmp/test_data}"
mkdir -p "$TEST_DATA_DIR"

echo "=== Tier 0: compile ==="
"$PY" -m compileall -q backend/services/worker_service.py backend/scripts/run_worker.py main.py

echo "=== Tier 1: fast core subset ==="
# Explicit high-value modules (marker coverage expands gradually in L4).
"$PY" -m pytest -q \
  tests/test_security_boundaries.py \
  tests/test_worker_production_path.py \
  tests/test_failure_injection_recovery.py \
  tests/test_local_operations.py \
  tests/test_object_storage_production_path.py \
  tests/test_llm_gateway_production_cutover.py \
  tests/test_local_profiles.py \
  --maxfail=1

if [[ -d frontend/node_modules ]]; then
  echo "=== Frontend typecheck (optional if node_modules present) ==="
  (cd frontend && npm run typecheck)
else
  echo "SKIP frontend typecheck (no node_modules; run npm ci in UI_API/frontend)"
fi

echo "test_fast: PASS"
