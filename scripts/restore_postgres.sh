#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/restore_postgres.sh <backup.dump>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=scripts/lib_postgres.sh
source "$SCRIPT_DIR/lib_postgres.sh"

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "ERROR: pg_restore not found. Install PostgreSQL client tools first." >&2
  exit 1
fi

backup_file="$1"
if [[ ! -f "$backup_file" ]]; then
  echo "ERROR: backup file not found: $backup_file" >&2
  exit 1
fi

postgres_export_app_env

pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" "$backup_file"

echo "PostgreSQL restore completed from: $backup_file"
