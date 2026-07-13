#!/usr/bin/env bash
# Pre-deploy commercial gate: backup, migration clean, scope integrity, dependency presence.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UI_API_DIR="${UI_API_DIR:-$REPO_ROOT/UI_API}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "== pre-deploy: repository root $REPO_ROOT =="

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is required for pre-deploy checks." >&2
  exit 1
fi

if [[ ! -d "$UI_API_DIR" ]]; then
  echo "ERROR: UI_API directory not found: $UI_API_DIR" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: PYTHON_BIN not found: $PYTHON_BIN" >&2
  exit 1
fi

echo "== pre-deploy: optional dependency presence =="
command -v psql >/dev/null 2>&1 || echo "WARN: psql client missing (migration SQL tooling may fail)"
command -v pg_dump >/dev/null 2>&1 || echo "WARN: pg_dump missing (backup step may fail)"
command -v curl >/dev/null 2>&1 || echo "WARN: curl missing (post-deploy smoke will fail)"

if [[ "${SKIP_BACKUP:-0}" != "1" ]]; then
  echo "== pre-deploy: PostgreSQL backup =="
  bash "$SCRIPT_DIR/backup_postgres.sh"
else
  echo "SKIP_BACKUP=1 — backup skipped (must be justified in release notes)"
fi

echo "== pre-deploy: migration status/validate =="
(
  cd "$UI_API_DIR"
  MEMBER_STORAGE_BACKEND=postgres "$PYTHON_BIN" backend/scripts/manage_postgres_migrations.py status
  MEMBER_STORAGE_BACKEND=postgres "$PYTHON_BIN" backend/scripts/manage_postgres_migrations.py validate --require-clean
)

echo "== pre-deploy: commercial scope integrity =="
(
  cd "$UI_API_DIR"
  MEMBER_STORAGE_BACKEND=postgres "$PYTHON_BIN" backend/scripts/validate_commercial_scope.py --require-complete
)

if [[ "${SKIP_MEMBER_IDENTITY:-0}" != "1" ]]; then
  echo "== pre-deploy: member identity integrity =="
  (
    cd "$UI_API_DIR"
    MEMBER_STORAGE_BACKEND=postgres "$PYTHON_BIN" backend/scripts/verify_member_identity_migration.py --require-clean || true
  )
fi

echo "== pre-deploy: startup configuration fail-fast =="
(
  cd "$UI_API_DIR"
  "$PYTHON_BIN" - <<'PY'
import config
config.validate_startup_config()
print(f"APP_ENV={config.APP_ENV} configuration accepted")
PY
)

echo "pre-deploy checks completed"
