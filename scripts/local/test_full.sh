#!/usr/bin/env bash
# Extended local regression (JSON backend). PostgreSQL integration is separate.
set -euo pipefail
# shellcheck source=scripts/local/_common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

PY="$(python_bin)"
cd "$UI_API_DIR"
export PYTHONPATH="${UI_API_DIR}/backend:${UI_API_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export APP_ENV="${APP_ENV:-test}"
export MEMBER_STORAGE_BACKEND="${MEMBER_STORAGE_BACKEND:-json}"
export DATABASE_URL="${DATABASE_URL:-}"
export TEST_DATA_DIR="${TEST_DATA_DIR:-$RUNTIME_DIR/tmp/test_data}"
mkdir -p "$TEST_DATA_DIR"

echo "=== Full JSON backend (excluding postgres integration modules) ==="
"$PY" -m pytest -q tests \
  --ignore=tests/postgres_worker_production_path_integration.py \
  --ignore=tests/postgres_scope_contract_integration.py \
  --ignore=tests/postgres_member_identity_integration.py \
  --ignore=tests/postgres_admin_identity_integration.py \
  --ignore=tests/postgres_device_identity_integration.py \
  --ignore=tests/postgres_order_checkout_integration.py \
  --ignore=tests/postgres_worker_jobs_integration.py \
  --ignore=tests/postgres_commercial_scope_integration.py

if [[ -d frontend/node_modules ]]; then
  echo "=== Frontend unit ==="
  (cd frontend && npm test -- --run)
else
  echo "SKIP frontend unit (no node_modules)"
fi

echo "test_full: PASS"
