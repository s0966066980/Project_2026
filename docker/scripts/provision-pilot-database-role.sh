#!/usr/bin/env bash
# Provision the least-privilege PostgreSQL runtime role the Pilot profile names.
#
# `config/profiles/local-pilot.env.example` sets DATABASE_RUNTIME_ROLE, and the
# migration grants that role table and sequence privileges — but nothing creates
# it, so a Pilot started from the shipped profile fails its first migration with
# `role "project_runtime" does not exist`. This script closes that gap.
#
# The role is created NOLOGIN on purpose. The application still connects as the
# owning role; a login credential that nothing uses would be a secret with no
# owner. Moving the runtime connection onto this role is Operations &
# Configuration work and needs its own credential handling.
#
# Creating the role is idempotent and additive. It never drops a role, a
# database, a table or a privilege.
#
# Usage:
#   bash docker/scripts/provision-pilot-database-role.sh [role-name]

set -euo pipefail

ROLE="${1:-${DATABASE_RUNTIME_ROLE:-project_runtime}}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-project-2026}"
CONTAINER="${POSTGRES_CONTAINER:-${PROJECT_NAME}-postgres-1}"
DB_USER="${POSTGRES_USER:-project_2026}"
DB_NAME="${POSTGRES_DB:-project_2026}"

if ! printf '%s' "$ROLE" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$'; then
  printf 'Refusing to use %s: not a safe PostgreSQL identifier.\n' "$ROLE" >&2
  exit 1
fi

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
  printf 'PostgreSQL container %s is not running.\n' "$CONTAINER" >&2
  exit 1
fi

printf 'Provisioning NOLOGIN role %s in %s/%s...\n' "$ROLE" "$CONTAINER" "$DB_NAME"

docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -c "
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${ROLE}') THEN
    CREATE ROLE ${ROLE} NOLOGIN;
  END IF;
END
\$\$;"

docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT rolname || ' canlogin=' || rolcanlogin FROM pg_roles WHERE rolname = '${ROLE}'"

printf 'Done. The migration grants this role its privileges on the next run.\n'
