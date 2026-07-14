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
# Reset tracked settings if a previous test polluted learning_data
if command -v git >/dev/null 2>&1; then
  git -C "$REPO_ROOT" checkout -- UI_API/learning_data/settings.json 2>/dev/null || true
fi

echo "=== Tier 0: compile ==="
"$PY" -m compileall -q backend/services/worker_service.py backend/scripts/run_worker.py main.py

echo "=== Tier 1: fast core subset ==="
"$PY" -m pytest -q \
  tests/test_security_boundaries.py \
  tests/test_worker_production_path.py \
  tests/test_failure_injection_recovery.py \
  tests/test_deployment_operations.py \
  tests/test_object_storage_production_path.py \
  tests/test_llm_gateway_production_cutover.py \
  --maxfail=1

if [[ -d frontend/node_modules ]]; then
  echo "=== Frontend typecheck (optional if node_modules present) ==="
  (cd frontend && npm run typecheck)
else
  echo "SKIP frontend typecheck (no node_modules; run npm ci in UI_API/frontend)"
fi

echo "test_fast: PASS"
