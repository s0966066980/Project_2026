#!/usr/bin/env bash
# Check a backup is what its manifest says, without touching the running system.
#
# This is the cheap check, run often. It answers "is this copy intact and
# self-describing", not "does it restore" — only restore_test.sh answers that,
# and a backup is not proven until it has.
#
# Usage:
#   bash scripts/backup/verify_backup.sh <backup-directory>
#   bash scripts/backup/verify_backup.sh --latest

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

TARGET="${1:-}"
[ -n "$TARGET" ] || die "usage: verify_backup.sh <backup-directory>|--latest"

if [ "$TARGET" = "--latest" ]; then
  TARGET="$(ls -1d "${BACKUP_ROOT}"/postgres/*/ 2>/dev/null | sort | tail -1)"
  [ -n "$TARGET" ] || die "no backup found under ${BACKUP_ROOT}/postgres"
fi
TARGET="${TARGET%/}"

MANIFEST="${TARGET}/manifest.json"
[ -f "$MANIFEST" ] || die "no manifest.json in ${TARGET}; an unidentified dump is not a backup"

FAILURES=0
check() {
  if [ "$2" = "$3" ]; then
    pass "$1"
  else
    fail "$1: expected ${2:-<empty>}, found ${3:-<empty>}"
    FAILURES=$((FAILURES + 1))
  fi
}

read_field() {
  python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ''))" "$MANIFEST" "$1"
}

KIND="$(read_field kind)"
ARTIFACT="$(read_field artifact)"
EXPECTED_SUM="$(read_field sha256)"
EXPECTED_SIZE="$(read_field size_bytes)"
SCHEMA_VERSION="$(read_field schema_version)"

note "verifying ${KIND} backup at ${TARGET}"

ARTIFACT_PATH="${TARGET}/${ARTIFACT}"
if [ ! -f "$ARTIFACT_PATH" ]; then
  die "manifest names ${ARTIFACT} but the file is not there"
fi

check "checksum matches the manifest" "$EXPECTED_SUM" "$(checksum_of "$ARTIFACT_PATH")"
check "size matches the manifest" "$EXPECTED_SIZE" "$(wc -c < "$ARTIFACT_PATH" | tr -d '[:space:]')"

case "$KIND" in
  postgres)
    if [ -z "$SCHEMA_VERSION" ]; then
      fail "manifest records no schema_version; the dump cannot be interpreted"
      FAILURES=$((FAILURES + 1))
    else
      pass "records schema ${SCHEMA_VERSION}"
    fi
    # pg_restore --list reads the archive's table of contents. A dump that
    # cannot be listed cannot be restored, and this finds that out now rather
    # than during an incident. The file is mounted rather than piped: a custom
    # format archive has to be seekable, so reading it from stdin fails on a
    # perfectly good dump.
    if docker run --rm --entrypoint pg_restore \
         -v "$(cd "$(dirname "$ARTIFACT_PATH")" && pwd)/$(basename "$ARTIFACT_PATH")":/backup.dump:ro \
         postgres:18.4-bookworm --list /backup.dump > /dev/null 2>&1; then
      pass "archive table of contents is readable"
    else
      fail "pg_restore cannot read the archive"
      FAILURES=$((FAILURES + 1))
    fi
    ;;
  objects)
    if tar -tzf "$ARTIFACT_PATH" > /dev/null 2>&1; then
      pass "archive is readable"
    else
      fail "archive is not readable"
      FAILURES=$((FAILURES + 1))
    fi
    ;;
  *)
    fail "unknown backup kind: ${KIND}"
    FAILURES=$((FAILURES + 1))
    ;;
esac

if [ "$FAILURES" -gt 0 ]; then
  fail "${FAILURES} check(s) failed"
  exit 1
fi
pass "backup verified; restore is still unproven until restore_test.sh passes"
