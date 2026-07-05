#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck source=scripts/lib_postgres.sh
source "$SCRIPT_DIR/lib_postgres.sh"

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "ERROR: pg_dump not found. Install PostgreSQL client tools first." >&2
  exit 1
fi

postgres_export_app_env

backup_dir="${POSTGRES_BACKUP_DIR:-$REPO_ROOT/backups/postgres}"
mkdir -p "$backup_dir"

timestamp="$(date +%Y%m%d_%H%M%S)"
output="${1:-$backup_dir/${POSTGRES_DB}_${timestamp}.dump}"

pg_dump --format=custom --no-owner --file "$output" "$DATABASE_URL"

echo "PostgreSQL backup written: $output"
