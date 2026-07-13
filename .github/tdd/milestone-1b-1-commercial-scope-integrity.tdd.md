# Milestone 1B.1 — Commercial Scope Integrity TDD Evidence

## Source and User Journeys

- As an operator, I need conflicting scope identifiers to fail closed so another Store or Device cannot overwrite commercial records.
- As an operator, I need PostgreSQL failures in staging/production to remain observable and never fall back to stale JSON.
- As operations, I need a read-only readiness and integrity check before enabling identity-based scope enforcement.

## Initial RED

`UI_API/tests/test_commercial_scope_integrity.py` executed before implementation: 13 failed because the shared conflict type, fallback policy, readiness service, and validator did not exist.

## Boundary RED

`UI_API/tests/postgres_commercial_scope_integration.py` reproduces same-Tenant cross-Store audit collision, same-Store cross-Device event/session collision, cross-Tenant collision, and null-safe tenant-level audit behavior.

## GREEN

Shared `CommercialScopeConflictError`, immutable session origin device, null-safe audit/event collision predicates, fail-closed PostgreSQL policy, readiness service, and aggregate validator are implemented.

- `pytest -q tests/test_commercial_scope_integrity.py`: 15 passed.
- Target tests: 61 passed.
- JSON backend: 203 passed.

## Security Verification

Production/staging PostgreSQL failures raise safe `PostgresOperationError`; JSON fallback is only allowed when development explicitly sets `ALLOW_POSTGRES_JSON_FALLBACK=true`. Conflict errors are never swallowed. Validator emits aggregate table/type/count only.

## Integration Verification

Disposable PostgreSQL 16 verification: `pytest -q tests/postgres_migration_integration.py tests/postgres_commercial_scope_integration.py`: 2 passed. `validate_commercial_scope.py --require-complete` returned valid with no violations.

## Known Limitations

- Scope columns remain nullable until a later forward enforcement migration.
- Member phone remains a global legacy primary key pending ADR-0004.
- No Admin identity, RBAC, device credential, UI, or public API was added.
