# Adopt a Local Single-Host PostgreSQL Runtime

Status: accepted

The current deployment target is one developer-operated host. PostgreSQL 18 runs locally through Docker Compose, listens only on `127.0.0.1:55432` on the host (standard port 5432 inside the container), and is selected exclusively by `DATABASE_BACKEND=postgresql` with `DATABASE_TOPOLOGY=single`. The nonstandard host port avoids modifying an unrelated host PostgreSQL already listening on 5432. This profile is suitable for local use and functional validation; it is explicitly not production high availability.

All mutable runtime data lives outside the Git repository beneath one guarded `RUNTIME_DATA_ROOT` (default `/home/oliver/.local/share/project-2026`). The runtime creates private, non-overlapping directories with mode `0700`:

| Directory | Owner / writer | Purpose |
| --- | --- | --- |
| `postgres/pgdata` | PostgreSQL container only | PostgreSQL data cluster |
| `postgres/wal-archive` | PostgreSQL container only | Local WAL archive |
| `backups/postgres` | Explicit backup command only | Logical or physical backup output |
| `sqlite` | Local Development/test adapter only | One local SQLite database |
| `objects` | Object-storage adapter | Uploaded and generated objects |
| `rag/indexes` | Retrieval-index adapter | Rebuildable RAG indexes |
| `logs` | Application and maintenance commands | Operational logs and probe receipts |
| `exports` | Explicit export workflows | User-requested exports |
| `imports` | Explicit import workflows | Staged import input |
| `tmp` | Application process | Disposable runtime work |

The PostgreSQL container mounts only `postgres/pgdata` and `postgres/wal-archive`, plus read-only initialization and Docker secret files. It cannot access objects, RAG indexes, backups, imports, exports, logs, SQLite, or temporary application files. Database migration and application runtime use distinct roles and secret files. Backup files remain on the same host in this phase and therefore do not constitute disaster recovery.

The future production topology is reserved as `DATABASE_TOPOLOGY=ha`: one primary, at least one synchronous standby, and at least one asynchronous standby placed on three cloud VMs in three availability zones. Production startup rejects `single`, and readiness accepts `ha` only when the connected node is primary and PostgreSQL reports both synchronous and asynchronous replicas. Cloud provisioning, replication orchestration, failover, fencing, backup off-host replication, DNS/service discovery, and TLS certificate distribution are deliberately not implemented in the local phase.

## Consequences

- Domains depend on the Runtime Persistence Profile interface, not Docker paths, replica hostnames, or failover mechanics.
- Moving from one host to three VMs changes deployment adapters and operational evidence, not domain repositories or transaction rules.
- `DATABASE_BACKEND` is the sole database selection switch. Legacy selection variables and JSON fallback are rejected.
- Local PostgreSQL may be functionally ready while still reporting `production_ha: false`.
- Existing JSON and dispersed SQLite records are not deleted until the new PostgreSQL runtime has started, reached the migration head, passed adapter coverage, and completed the explicit rollback-only write probe.
