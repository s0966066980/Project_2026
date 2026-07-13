# Restore Drill Record

- date (UTC): 2026-07-13T14:04:45Z
- source version: 8a3c285
- source backup: NOT_PROVIDED
- target: ISOLATED_TARGET_NOT_SET
- mode: dry-run
- operator: oliver
- duration: PENDING
- row counts: PENDING
- migration: PENDING
- smoke: PENDING

## Procedure notes

1. Prefer restoring into an isolated database, never directly overwriting production.
2. Validate migration status/validate --require-clean after restore.
3. Run commercial scope validator (count-only) and post-deploy smoke against the isolated target.
4. Record go/no-go and residual risk. This record is **NOT Production Certified**.


## Dry-run result

- duration: 0s
- No database restore was executed.
- Scripts validated present: backup_postgres.sh, restore_postgres.sh, pre_deploy_check.sh, post_deploy_smoke.sh
