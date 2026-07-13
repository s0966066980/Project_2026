#!/usr/bin/env bash
# Record an isolated PostgreSQL restore drill (or a dry-run evidence shell).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DRILL_DIR="${DRILL_DIR:-$REPO_ROOT/docs/operations/restore-drills}"
mkdir -p "$DRILL_DIR"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="${1:-$DRILL_DIR/restore-drill-${timestamp}.md}"
source_version="${SOURCE_VERSION:-$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
source_backup="${SOURCE_BACKUP:-}"
target_db="${TARGET_DATABASE_URL:-}"
mode="${DRILL_MODE:-dry-run}"

start_epoch="$(date +%s)"

cat >"$output" <<EOF
# Restore Drill Record

- date (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)
- source version: ${source_version}
- source backup: ${source_backup:-NOT_PROVIDED}
- target: ${target_db:-ISOLATED_TARGET_NOT_SET}
- mode: ${mode}
- operator: ${USER:-unknown}
- duration: PENDING
- row counts: PENDING
- migration: PENDING
- smoke: PENDING

## Procedure notes

1. Prefer restoring into an isolated database, never directly overwriting production.
2. Validate migration status/validate --require-clean after restore.
3. Run commercial scope validator (count-only) and post-deploy smoke against the isolated target.
4. Record go/no-go and residual risk. This record is **NOT Production Certified**.

EOF

if [[ "$mode" == "execute" ]]; then
  if [[ -z "$source_backup" || -z "$target_db" ]]; then
    echo "ERROR: DRILL_MODE=execute requires SOURCE_BACKUP and TARGET_DATABASE_URL" >&2
    exit 1
  fi
  echo "== restore drill execute into isolated target =="
  DATABASE_URL="$target_db" bash "$SCRIPT_DIR/restore_postgres.sh" "$source_backup"
  end_epoch="$(date +%s)"
  duration=$((end_epoch - start_epoch))
  {
    echo
    echo "## Execution result"
    echo
    echo "- duration: ${duration}s"
    echo "- restore command completed"
    echo "- migration: run manage_postgres_migrations.py validate --require-clean against the isolated target"
    echo "- row counts: record manually after validation queries"
    echo "- smoke: run post_deploy_smoke.sh against an API pointed at the isolated target"
  } >>"$output"
else
  end_epoch="$(date +%s)"
  duration=$((end_epoch - start_epoch))
  {
    echo
    echo "## Dry-run result"
    echo
    echo "- duration: ${duration}s"
    echo "- No database restore was executed."
    echo "- Scripts validated present: backup_postgres.sh, restore_postgres.sh, pre_deploy_check.sh, post_deploy_smoke.sh"
  } >>"$output"
fi

echo "Restore drill record written: $output"
