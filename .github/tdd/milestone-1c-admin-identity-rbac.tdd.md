# Milestone 1C — Admin Identity / RBAC TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1C.

- As an administrator, I can authenticate with an individual identity and receive a short-lived server session without exposing its token.
- As a tenant or store administrator, I can perform only actions allowed by my scoped permissions.
- As an operator, I can revoke or expire sessions without leaving reusable plaintext credentials.
- As a legacy deployment, I can use the shared token only during an explicitly enabled compatibility window.

## Initial RED

Command:

```bash
UI_API/.venv/bin/python -m pytest -q UI_API/tests/test_admin_identity_foundation.py
```

Result: **RED — 10 failed**. Failures were caused by the intentionally missing `0003` migration and the missing admin identity model, repository, service, authorization, route, and compatibility policy. The test module collected successfully; no unrelated setup or syntax failure caused the RED state.

## Boundary RED

The initial contract suite also failed on missing tenant/store authorization and legacy-flag behavior. PostgreSQL boundary coverage was then added for a fresh 0001→0003 apply, cross-tenant role assignment, hashed credential persistence, atomic rotation, revocation, and clean reapply.

## GREEN

Core GREEN command:

```bash
UI_API/.venv/bin/python -m pytest -q UI_API/tests/test_admin_identity_foundation.py
```

Result after implementation: **10 passed**. Final hardened suite: **16 passed**.

Full JSON compatibility command:

```bash
MEMBER_STORAGE_BACKEND=json DATABASE_URL= .venv/bin/python -m pytest -q tests
```

Result: **219 passed**.

## Security Verification

- Argon2id hash/verify/rehash, generic unknown/disabled login error, and SHA-256 session token hash: PASS.
- Permission, tenant, and store denial plus stable permission catalog: PASS.
- `HttpOnly`, production `Secure`, `SameSite=Strict` cookie and no raw token response: PASS.
- Legacy Admin token requires explicit flag, is audited, and production can run with it disabled: PASS.
- Verified principal overrides untrusted `X-Admin-User`; client scope headers never define identity scope: PASS.
- Admin WebSocket uses the same HttpOnly session cookie; the new frontend does not place Admin credentials in URLs: PASS.

## Integration Verification

- Fresh PostgreSQL 0001→0003, commercial scope upgrade, Admin identity/RBAC integration: **3 passed**.
- `validate_commercial_scope.py --require-complete`: PASS, no violations.
- `manage_postgres_migrations.py validate --require-clean`: PASS, three applied checksums and no pending migration.
- Ruff lint/format for the CI gradual scope expanded with every new identity module: PASS.
- mypy: PASS (29 source files).
- Frontend TypeScript and JavaScript syntax: PASS.
- Shell syntax: PASS.
- Python 3.10 runtime matrix: NOT RUN locally because Python 3.10 is unavailable; GitHub Actions retains the 3.10 job.

Coverage combines the unit and PostgreSQL identity suites. New 1C modules total **86%** (300 statements, 43 missed); model and authorization policy are 100%, repository 89%, identity service 89%, route 63%.

## Known Limitations

- Milestone 1C provides only the necessary login/session bootstrap surface; broad Admin UI refactoring remains out of scope.
- Device identity and member UUID/PII migration remain later milestones.
- Full Admin user/role management UI, MFA, and external OIDC are not part of this foundation.
- The expanded all-backend Ruff baseline still contains pre-existing debt outside the gradual CI scope.
