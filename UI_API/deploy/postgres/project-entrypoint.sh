#!/bin/sh
set -eu

private_secret_dir=/run/project-2026-secrets
install -d -m 0700 -o postgres -g postgres "$private_secret_dir"
install -m 0400 -o postgres -g postgres \
  /run/secrets/postgres_runtime_password \
  "$private_secret_dir/postgres_runtime_password"

exec /usr/local/bin/docker-entrypoint.sh "$@"
