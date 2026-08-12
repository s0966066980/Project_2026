#!/usr/bin/env bash
# Copy the runtime data a restore cannot rebuild from the database.
#
# Deliberately narrow. Model weights and container images are re-obtainable and
# are not business data, so they are not backed up — the model registry records
# what to re-obtain instead. Logs, imports, exports, the SQLite test substrate
# and tmp are working files, not authority, and copying them would make every
# backup bigger and less clearly about anything.
#
# What is here: stored objects, and the RAG index. The index is derived from
# published knowledge and can be rebuilt, but rebuilding it costs a warm-up an
# operator may not have during a recovery, so a copy is kept.
#
# Usage:
#   bash scripts/backup/backup_objects.sh [--label LABEL]

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

LABEL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL="${2:-}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

require_container "$APP_CONTAINER"

RUNTIME_ROOT="$(docker exec "$APP_CONTAINER" printenv RUNTIME_DATA_ROOT 2>/dev/null || echo /var/lib/project-2026)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="${STAMP}${LABEL:+-${LABEL}}"
DESTINATION="${BACKUP_ROOT}/objects/${NAME}"
mkdir -p "$DESTINATION"

ARCHIVE="${DESTINATION}/runtime-data.tar.gz"
INCLUDED=""
for class in objects rag; do
  if docker exec "$APP_CONTAINER" test -d "${RUNTIME_ROOT}/${class}"; then
    INCLUDED="${INCLUDED} ${class}"
  fi
done
[ -n "$INCLUDED" ] || { rm -rf "$DESTINATION"; die "no backup-scoped data classes found under ${RUNTIME_ROOT}"; }

note "archiving${INCLUDED} from ${RUNTIME_ROOT}"
# shellcheck disable=SC2086
if ! docker exec "$APP_CONTAINER" tar -czf - -C "$RUNTIME_ROOT" $INCLUDED > "$ARCHIVE"; then
  rm -rf "$DESTINATION"
  die "archive failed; no partial backup left behind"
fi
[ -s "$ARCHIVE" ] || { rm -rf "$DESTINATION"; die "archive is empty"; }

ENTRIES="$(tar -tzf "$ARCHIVE" | wc -l | tr -d '[:space:]')"
CHECKSUM="$(checksum_of "$ARCHIVE")"
SIZE="$(wc -c < "$ARCHIVE" | tr -d '[:space:]')"

cat > "${DESTINATION}/manifest.json" <<JSON
{
  "kind": "objects",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "runtime_data_root": "$(json_escape "$RUNTIME_ROOT")",
  "classes": "$(json_escape "$(echo $INCLUDED | tr -s ' ')")",
  "app_revision": "$(json_escape "$(app_version)")",
  "artifact": "$(json_escape "$(basename "$ARCHIVE")")",
  "entry_count": ${ENTRIES:-0},
  "size_bytes": ${SIZE:-0},
  "sha256": "$(json_escape "$CHECKSUM")",
  "excluded": "model weights and images are re-obtainable; logs, imports, exports, sqlite and tmp are not authority"
}
JSON

pass "object backup written to ${DESTINATION}"
note "  ${ENTRIES} entries, ${SIZE} bytes, sha256 ${CHECKSUM:0:16}…"
printf '%s\n' "$DESTINATION"
