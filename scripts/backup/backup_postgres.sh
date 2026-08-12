#!/usr/bin/env bash
# Take a restorable copy of the authoritative database.
#
# The dump is custom format so a restore can be selective and so pg_restore can
# read its table of contents without a server — which is how verify_backup.sh
# checks a copy is readable without touching the running database.
#
# Every backup records what it is: when, which schema, which build. A dump whose
# schema version is unknown cannot be restored with any confidence, because
# nothing says which application it belongs to.
#
# Usage:
#   bash scripts/backup/backup_postgres.sh [--label LABEL]
#   BACKUP_ROOT=/mnt/external bash scripts/backup/backup_postgres.sh

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

LABEL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL="${2:-}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

require_container "$POSTGRES_CONTAINER"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${STAMP}${LABEL:+-${LABEL}}"
DESTINATION="${BACKUP_ROOT}/postgres/${NAME}"
mkdir -p "$DESTINATION"

DUMP="${DESTINATION}/${POSTGRES_DB}.dump"
note "dumping ${POSTGRES_DB} from ${POSTGRES_CONTAINER}"
if ! docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      --format=custom --no-owner --no-privileges > "$DUMP"; then
  rm -rf "$DESTINATION"
  die "pg_dump failed; no partial backup left behind"
fi

# A zero-length or truncated dump is the failure mode that looks like success
# until the day it is needed.
[ -s "$DUMP" ] || { rm -rf "$DESTINATION"; die "pg_dump produced an empty file"; }

SCHEMA_VERSION="$(database_schema_version)"
FINGERPRINT="$(schema_fingerprint)"
TABLES="$(table_count)"
APP_REVISION="$(app_version)"
CHECKSUM="$(checksum_of "$DUMP")"
SIZE="$(wc -c < "$DUMP" | tr -d '[:space:]')"

cat > "${DESTINATION}/manifest.json" <<JSON
{
  "kind": "postgres",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "database": "$(json_escape "$POSTGRES_DB")",
  "schema_version": "$(json_escape "$SCHEMA_VERSION")",
  "schema_fingerprint": "$(json_escape "$FINGERPRINT")",
  "table_count": ${TABLES:-0},
  "app_revision": "$(json_escape "$APP_REVISION")",
  "artifact": "$(json_escape "$(basename "$DUMP")")",
  "size_bytes": ${SIZE:-0},
  "sha256": "$(json_escape "$CHECKSUM")",
  "format": "pg_dump custom"
}
JSON

pass "postgres backup written to ${DESTINATION}"
note "  schema ${SCHEMA_VERSION}, ${TABLES} tables, ${SIZE} bytes, sha256 ${CHECKSUM:0:16}…"
printf '%s\n' "$DESTINATION"
