#!/usr/bin/env bash
# Shared helpers for the backup and restore scripts. Sourced, never run.
#
# One place for the things every script here has to agree on: where backups go,
# which container holds the database, and how a backup names itself. When those
# disagree between scripts, a backup verifies against the wrong copy and the
# drill proves nothing.

set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-project-2026}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-${PROJECT_NAME}-postgres-1}"
APP_CONTAINER="${APP_CONTAINER:-${PROJECT_NAME}-app-1}"
POSTGRES_DB="${POSTGRES_DB:-project_2026}"
POSTGRES_USER="${POSTGRES_USER:-project_2026}"

# A backup kept only inside the runtime it protects is not a backup. The default
# stays on this host so the drill can run unattended, and BACKUP_ROOT is the
# single knob an operator sets to put copies somewhere the primary cannot lose
# them with itself (see Pilot Recovery Objective in CONTEXT.md).
BACKUP_ROOT="${BACKUP_ROOT:-${REPO_ROOT}/.backups}"

note() { printf '%s\n' "$*"; }
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; }

die() { fail "$*"; exit 1; }

require_container() {
  local name="$1"
  docker inspect "$name" >/dev/null 2>&1 || die "container ${name} is not running; bring the stack up first"
}

# The migration head the database is actually at, which is what a restore has to
# be interpreted against. The build's head lives in /api/v1/operations/build and
# the two differ exactly when a deployment is half-applied.
database_schema_version() {
  docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1" 2>/dev/null | tr -d '[:space:]'
}

# A fingerprint of the applied migration ledger. Two databases with the same
# value have the same schema history; a mismatch after a restore means the copy
# is not the schema the dump claimed.
schema_fingerprint() {
  local database="${1:-$POSTGRES_DB}"
  docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$database" -tAc \
    "SELECT md5(string_agg(version || ':' || checksum, ',' ORDER BY version)) FROM schema_migrations" \
    2>/dev/null | tr -d '[:space:]'
}

table_count() {
  local database="${1:-$POSTGRES_DB}"
  docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$database" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null | tr -d '[:space:]'
}

app_version() {
  docker exec "$APP_CONTAINER" printenv APP_GIT_REVISION 2>/dev/null || echo unknown
}

checksum_of() {
  sha256sum "$1" | awk '{print $1}'
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}
