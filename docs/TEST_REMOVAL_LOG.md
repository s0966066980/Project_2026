# Test Removal / Merge Log (Local-first L4+)

| Date | Test path | Action | Reason | Replacement coverage | Risk | Verification |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-07-14 | `tests/test_rag_governance_durable.py::test_migration_0010_defines_rag_tables` | REMOVE_REDUNDANT | SQL keyword existence only | `test_member_storage_migration.py::test_membership_postgres_migrations_are_versioned` + 0010 file checksum | low | `pytest -q tests/test_member_storage_migration.py` |
| 2026-07-14 | `tests/test_control_plane_durable.py::test_migration_0011_control_plane_tables` | REMOVE_REDUNDANT | SQL keyword existence only | same migration version inventory | low | same |
| 2026-07-14 | docker Dockerfile/compose path assertions | REPLACED in L1 | Docker no longer active runtime | `test_deployment_operations.py` native local docs + archive presence | low | `pytest -q tests/test_deployment_operations.py` |

## Kept despite inventory heuristic

- Architecture import boundary tests (e.g. no direct `ai_services` in production services)
- Unscoped repository caller scans
- Permission policy scans

These look like file/string tests but protect production cutover rules.
