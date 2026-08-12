# Recovery evidence

## Restore drill — 2026-08-12

"There is a backup script" is not recovery. A dump verifies its own checksum
happily while being unrestorable, so the only evidence that counts is a restore
that came back.

Taken from the running stack (PostgreSQL 18.4, 79 tables):

```text
backup_postgres.sh --label drill
  schema 0028_optimization_lab, 79 tables, 1886357 bytes, sha256 e4f11c688ae729d6…

backup_objects.sh --label drill
  9 entries, 44734 bytes, sha256 db774648377a4faa…

verify_backup.sh --latest
  PASS checksum matches the manifest
  PASS size matches the manifest
  PASS records schema 0028_optimization_lab
  PASS archive table of contents is readable

restore_test.sh --latest
  PASS pg_restore completed
  PASS schema fingerprint (650fdf9f749c1994fd585177613f0f21)
  PASS table count (79)
  PASS schema version (0028_optimization_lab)
  PASS store_menu_items row count (138)
  PASS schema_migrations row count (28)
  PASS restore drill passed
```

The drill restores into a temporary database and drops it on the way out. The
primary database is never written to.

## The drill was made to fail before it was believed

| Mutation | Result |
| --- | --- |
| append bytes to the dump | `verify_backup.sh` failed on checksum and size |
| zero the first 200 KB of the dump | `restore_test.sh` failed: "this backup does not restore" |
| edit `table_count` in the manifest to 42 | `restore_test.sh` failed on the table-count mismatch |

After each failing run, `pg_database` held zero `restore_drill_%` databases: the
cleanup trap fires on the failure path, which is the path that matters.

## What is not covered

- **Separation.** `BACKUP_ROOT` defaults inside the checkout so the drill can
  run unattended. A copy that lives only on the host it protects does not meet
  the Pilot Recovery Objective; pointing `BACKUP_ROOT` at separated storage is
  an operator action this repository cannot perform or verify.
- **RPO and RTO.** One hour and four hours are declared in `CONTEXT.md`. This
  drill measures neither; it proves restorability, not timing under load.
- **Scheduling and retention.** The roadmap suggests 7 daily, 4 weekly, 3
  monthly. Nothing here runs on a timer yet — that belongs with the appliance
  work (items 30–31), where a systemd timer has somewhere to live.
- **Application-level recovery.** The drill checks the database came back. It
  does not start the application against the restored copy or place an order
  through it; that needs the full stack pointed at a restored database, which
  is a deployment rehearsal rather than a backup check.
