#!/usr/bin/env bash
# Restore a backup into a throwaway database and prove it came back.
#
# "There is a backup script" is not recovery. This is the check that decides
# whether the backup means anything, and it is the only one that can: a dump
# verifies its own checksum happily while being unrestorable.
#
# It never touches the primary database. The restore target is a temporary
# database created for the run and dropped at the end, including on failure.
#
# Usage:
#   bash scripts/backup/restore_test.sh <backup-directory>
#   bash scripts/backup/restore_test.sh --latest
#   KEEP_RESTORED_DATABASE=1 bash scripts/backup/restore_test.sh --latest   # for inspection

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TARGET="${1:-}"
[ -n "$TARGET" ] || die "usage: restore_test.sh <backup-directory>|--latest"
if [ "$TARGET" = "--latest" ]; then
  TARGET="$(ls -1d "${BACKUP_ROOT}"/postgres/*/ 2>/dev/null | sort | tail -1)"
  [ -n "$TARGET" ] || die "no backup found under ${BACKUP_ROOT}/postgres"
fi
TARGET="${TARGET%/}"
MANIFEST="${TARGET}/manifest.json"
[ -f "$MANIFEST" ] || die "no manifest.json in ${TARGET}"

require_container "$POSTGRES_CONTAINER"

read_field() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$MANIFEST" "$1"
}

ARTIFACT="${TARGET}/$(read_field artifact)"
EXPECTED_SCHEMA="$(read_field schema_version)"
EXPECTED_FINGERPRINT="$(read_field schema_fingerprint)"
EXPECTED_TABLES="$(read_field table_count)"

RESTORE_DB="restore_drill_$(date -u +%Y%m%d%H%M%S)_$$"
FAILURES=0

cleanup() {
  if [ "${KEEP_RESTORED_DATABASE:-0}" = "1" ]; then
    note "keeping ${RESTORE_DB} for inspection"
    return
  fi
  docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "DROP DATABASE IF EXISTS ${RESTORE_DB}" > /dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

check() {
  if [ "$2" = "$3" ]; then
    pass "$1 (${2})"
  else
    fail "$1: backup says ${2:-<empty>}, restored database has ${3:-<empty>}"
    FAILURES=$((FAILURES + 1))
  fi
}

note "restoring ${TARGET} into ${RESTORE_DB}"
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "CREATE DATABASE ${RESTORE_DB}" > /dev/null || die "could not create the restore target"

if ! docker exec -i "$POSTGRES_CONTAINER" pg_restore -U "$POSTGRES_USER" -d "$RESTORE_DB" \
      --no-owner --no-privileges < "$ARTIFACT" > /dev/null 2>&1; then
  die "pg_restore failed; this backup does not restore"
fi
pass "pg_restore completed"

check "schema fingerprint" "$EXPECTED_FINGERPRINT" "$(schema_fingerprint "$RESTORE_DB")"
check "table count" "$EXPECTED_TABLES" "$(table_count "$RESTORE_DB")"

RESTORED_SCHEMA="$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" -tAc \
  "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1" 2>/dev/null | tr -d '[:space:]')"
check "schema version" "$EXPECTED_SCHEMA" "$RESTORED_SCHEMA"

# Row counts on the tables a store would notice missing. A restore that brings
# back an empty catalog is a restore that technically succeeded.
for table in store_menu_items schema_migrations; do
  EXISTS="$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" -tAc \
    "SELECT to_regclass('public.${table}') IS NOT NULL" 2>/dev/null | tr -d '[:space:]')"
  if [ "$EXISTS" != "t" ]; then
    fail "${table} is missing from the restored database"
    FAILURES=$((FAILURES + 1))
    continue
  fi
  SOURCE_ROWS="$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT count(*) FROM ${table}" 2>/dev/null | tr -d '[:space:]')"
  RESTORED_ROWS="$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$RESTORE_DB" -tAc \
    "SELECT count(*) FROM ${table}" 2>/dev/null | tr -d '[:space:]')"
  check "${table} row count" "$SOURCE_ROWS" "$RESTORED_ROWS"
done

if [ "$FAILURES" -gt 0 ]; then
  fail "restore drill failed with ${FAILURES} mismatch(es)"
  exit 1
fi
pass "restore drill passed for ${TARGET}"
