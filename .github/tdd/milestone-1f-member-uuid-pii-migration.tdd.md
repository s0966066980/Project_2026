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

The first PostgreSQL GREEN attempt exposed a 25-column/24-placeholder Member insert and the historical Milestone 1B assertion that rejected the same phone across tenants. Both failed before implementation was corrected. The full JSON suite then exposed an obsolete ADR assertion that still required `Implementation Status: Deferred`.

## GREEN

- `pytest -q tests/test_member_identity_migration.py tests/test_member_service_admin.py tests/test_member_service_core.py tests/test_member_storage_migration.py`: PASS.
- Full JSON backend: PASS, 243 tests.
- PostgreSQL 0001→0006 legacy upgrade, idempotent backfill, same-phone tenant isolation, child references, rotation and anonymization: PASS.
- All historical PostgreSQL integrations from Milestone 1A through 1F: PASS.

## Security Verification

- Tenant-scoped HMAC-SHA256 lookup uses versioned managed pepper material; ordinary unsalted hashes are not used.
- Phone ciphertext uses Fernet authenticated encryption and safe decrypt errors do not echo ciphertext.
- Production/Staging key material is environment/Secret-Manager supplied; deterministic keys are restricted to Development/Test.
- Admin views/exports use masked phone; verifier output contains only violation types and counts.
- UUID anonymization clears lookup hash, ciphertext, key version, consent fields and child records while preserving a non-PII lifecycle tombstone.

## Integration Verification

- Ruff affected scope: PASS.
- Ruff format affected scope: PASS.
- Mypy: PASS, 37 source files.
- Python 3.12 application import: PASS. Python 3.10 runtime is covered by CI but was not locally available.
- Frontend `npm ci --ignore-scripts`, typecheck and syntax: PASS.
- Shell syntax and `git diff --check`: PASS.

## Known Limitations

- External Secret Manager/KMS wiring requires deployment-owned infrastructure; environment-backed contract is implemented locally and external wiring must not be claimed without real integration.
- Phone lookup is identity discovery, not authentication proof; OTP/PIN remains separate.
- Legal/privacy approval remains a manual commercial gate.
- Phone compatibility data remains until `uuid_only` production evidence supports a separate forward contract migration.
