# Milestone 1B.1 — Commercial Scope Integrity TDD Evidence

## Source and User Journeys

- As an operator, I need conflicting scope identifiers to fail closed so another Store or Device cannot overwrite commercial records.
- As an operator, I need PostgreSQL failures in staging/production to remain observable and never fall back to stale JSON.
- As operations, I need a read-only readiness and integrity check before enabling identity-based scope enforcement.

## Initial RED

Pending: `tests/test_commercial_scope_integrity.py` is added before implementation.

## Boundary RED

Pending: PostgreSQL integration will reproduce audit Store, recommendation Device, and session origin-device collisions.

## GREEN

Pending implementation and verification.

## Security Verification

Pending.

## Integration Verification

Pending.

## Known Limitations

- Scope columns remain nullable until a later forward enforcement migration.
- Member phone remains a global legacy primary key pending ADR-0004.
