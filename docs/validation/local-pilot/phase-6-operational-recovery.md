# Phase 6 — Local Operational Recovery Evidence

- Evidence date: 2026-07-28 (Asia/Taipei)
- Status: **Backup/restore and retention passed; controlled interruption matrix pending**
- Revision: `723f87c` on `main`
- Worktree: dirty; evidence applies to the tested working tree
- Runtime profile: `local-pilot`
- PostgreSQL: server 18.4, single-host primary
- Database fingerprint: `e2343247250475d8`
- Migration head: `0022_checkout_pickup_number`

## Runtime and data paths

`manage_runtime_persistence.py status` reports PostgreSQL as both configured and
effective backend, 19/19 adapter coverage, no pending migrations, a successful
rollback-only write probe, and separated runtime roots for PostgreSQL data/WAL,
backups, SQLite test/profile data, objects, RAG indexes, logs, exports, imports,
and temporary files. Every listed directory exists with mode `0700`.

SQLite is not the commercial source of truth in this profile and does not conflict
with PostgreSQL. It remains available for isolated tests/profile implementations.

## Backup and isolated restore: passed

The first backup attempt correctly failed because the host `pg_dump` major was 16
while the server major was 18. Its zero-byte output was deleted and its isolated
validation database was removed. PostgreSQL client 18.4 was then installed in the
user-owned runtime tools directory without replacing the system client or changing
the application Python environment.

Retained backup:

- file: `/home/oliver/.local/share/project-2026/backups/postgres/project_2026-20260728T130527Z.dump`;
- format/tool: PostgreSQL 18.4 custom dump;
- size: 5,120,419 bytes;
- mode: `0600`;
- SHA-256: `06679111c82d1379f1cbff16d48e12ac734423ab43988029e427f34e2cab37e8`.

The dump was restored into a uniquely named isolated validation database. Source
and restored representative counts matched:

| Record | Source | Restored |
| --- | ---: | ---: |
| schema migrations | 22 | 22 |
| Admin users | 1 | 1 |
| members | 0 | 0 |
| orders | 0 | 0 |
| Knowledge Items | 1 | 1 |
| Published Knowledge pointers | 1 | 1 |
| Voice Turns | 63 | 63 |

Both databases reported migration head `0022_checkout_pickup_number`; the isolated
database passed a rollback-only write probe. The active database was never used as
a restore target, and all validation databases were removed afterward
(`remaining_restore_databases=0`).

This is **same-host local recovery evidence only**. It does not protect against
loss of the host and is not off-host disaster recovery.

## Cleanup and restart observations

The configured-store cleanup cycle completed without the former missing-`path`
constructor warnings:

- Voice Turn retention: 0 expired rows removed;
- Knowledge artifact cleanup: no failed attempts;
- Checkout outbox dispatch: no failed events;
- diagnostic/log retention: enabled at 90 days, 59 records retained, 0 expired;
- no temporary or isolated restore database was left behind.

UI_API, the reliable worker, and R1-Omni were restarted during validation. Current
`/live` is live, `/ready` is ready, PostgreSQL connection/migrations/scope are
healthy, and R1-Omni reports its model loaded. Automated tests cover publication
resume, Voice replay/idempotency, Checkout/outbox idempotency, and cleanup.

## Remaining controlled scenarios

A new, observed matrix that independently stops PostgreSQL and Ollama during
accepted work has not been executed on this live host. Performing those disruptive
tests without the designated operator's timing would interrupt the currently
running pilot. The automated recovery contracts and repeated ordinary process
restarts pass, but Phase 6 remains formally open until the operator schedules and
witnesses the controlled interruption matrix.
