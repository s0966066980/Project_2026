# Restore Drill Template

Use this template for every isolated restore drill. Copy into `docs/operations/restore-drills/` or generate via `scripts/record_restore_drill.sh`.

## Required fields

| Field | Value |
| --- | --- |
| date (UTC) | |
| source version (git SHA / release tag) | |
| source backup path + checksum | |
| target (isolated database URL host/name only — no password) | |
| duration | |
| row counts (members / orders / outbox pending) | |
| migration status | clean / pending / mismatch |
| smoke (`/live`, `/ready`) | pass / fail |
| operator | |
| go / no-go | |

## Procedure

1. Declare maintenance or lab window; never restore over the only production database first.
2. Take or select a verified `pg_dump --format=custom` backup; record SHA-256.
3. Provision an **isolated** target database.
4. `DATABASE_URL=<isolated> bash scripts/restore_postgres.sh <backup.dump>`
5. Run migration `status` and `validate --require-clean`.
6. Run commercial scope validator (counts only; no PII).
7. Point a temporary API at the isolated target and run `scripts/post_deploy_smoke.sh`.
8. Record residual risk and whether production cutover is approved.

## Safety

- Prefer isolated target always.
- Do not paste DATABASE_URL passwords into tickets or the drill record.
- This drill evidence is **NOT Production Certified** by itself.
