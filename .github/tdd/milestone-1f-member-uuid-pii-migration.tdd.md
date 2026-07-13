# Milestone 1F — Member UUID / PII Migration TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1F, and ADR-0004.

- A member has an opaque UUID independent of phone PII.
- The same normalized phone can exist in different tenants, but not twice in one tenant.
- Phone lookup is tenant-scoped and keyed; stored ciphertext never contains plaintext.
- Existing Kiosk phone login remains compatible while reads/writes move through dual and UUID-preferred modes.
- Operators can backfill and verify references without printing phone, ciphertext, key, or pepper.

## Scope / Migration Strategy

`0006` uses expand → dual reference/backfill → verify → switch-ready contract. It keeps the phone compatibility column but moves the member PK to UUID and adds `member_id` references to preferences, sessions, and orders. No earlier migration is modified.

## Initial RED

Command: `pytest -q tests/test_member_identity_migration.py`.

Result: **RED — 6 failed**. The failures prove the missing 0006 UUID migration, Key Provider/PII service, feature flags/dependency declaration, UUID repository contract, and count-only verifier.

## Boundary RED

Pending key rotation, cross-tenant same-phone, drift/orphan, production fail-closed, and upgrade integration.

## GREEN

Pending.

## Security Verification

Pending keyed lookup, authenticated encryption, safe errors, masking, and no PII output.

## Integration Verification

Pending target/full JSON/PostgreSQL/static/frontend/shell gates.

## Known Limitations

- External Secret Manager/KMS wiring requires deployment-owned infrastructure; environment-backed contract is implemented locally and external wiring must not be claimed without real integration.
- Phone lookup is identity discovery, not authentication proof; OTP/PIN remains separate.
- Legal/privacy approval remains a manual commercial gate.
