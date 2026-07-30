#!/bin/sh
set -eu

runtime_password="$(cat "${POSTGRES_RUNTIME_PASSWORD_FILE:-/run/project-2026-secrets/postgres_runtime_password}")"

psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=runtime_password="$runtime_password" <<'SQL'
SELECT format('CREATE ROLE project_runtime LOGIN PASSWORD %L', :'runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'project_runtime')
\gexec

GRANT CONNECT ON DATABASE project_2026 TO project_runtime;
GRANT USAGE ON SCHEMA public TO project_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE project_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO project_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE project_migrator IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO project_runtime;
SQL
