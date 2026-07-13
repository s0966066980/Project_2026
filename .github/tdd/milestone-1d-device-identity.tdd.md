# Milestone 1D — Device Identity Foundation TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1D.

- As a kiosk device, I authenticate with an individual rotatable credential and receive a short-lived session.
- As an operator, I can issue, rotate, and revoke one device without affecting other devices.
- As the server, I derive tenant/store/device scope only from verified database ownership.
- As a legacy deployment, I can use the shared Kiosk token only during an explicitly enabled compatibility window.

## Initial RED

Command:

```bash
UI_API/.venv/bin/python -m pytest -q UI_API/tests/test_device_identity_foundation.py
```

Result: **RED — 9 failed**. The test module collected successfully. Failures were caused only by the intentionally missing 0004 migration, typed device model, credential/session service, route, and legacy compatibility policy.

## Boundary RED

The initial RED also covered disabled/revoked/expired credentials, header override, production legacy-off, and secure cookie. PostgreSQL boundary coverage was added for hierarchy FK, rotation overlap/cutover, credential/session revoke, safe events, and clean reapply.

## GREEN

Core command:

```bash
UI_API/.venv/bin/python -m pytest -q UI_API/tests/test_device_identity_foundation.py
```

Result after core implementation: **9 passed**. Final hardened suite: **12 passed**.

Full JSON compatibility:

```bash
MEMBER_STORAGE_BACKEND=json DATABASE_URL= .venv/bin/python -m pytest -q tests
```

Result: **231 passed**.

## Security Verification

- Credential/session hashes contain no raw secret; issue/rotate return credential only once: PASS.
- Device scope is loaded from database ownership and ignores client scope headers: PASS.
- Revoked, expired, disabled, wrong, and post-grace credentials are denied: PASS.
- Admin `device_identity.manage` permission and store scope required for issue/rotate/revoke: PASS.
- Production secure HttpOnly/SameSite cookie, rate limit, generic error, and legacy-off startup: PASS.
- Device events contain scope/type/count-safe metadata and no credential/session secret: PASS.
- WebSocket supports formal device session cookie; legacy URL token remains flag-gated compatibility only: PASS.

## Integration Verification

- Fresh PostgreSQL 0001→0004 plus scope/Admin/device integrations: **4 passed**.
- `validate_commercial_scope.py --require-complete`: PASS.
- `manage_postgres_migrations.py validate --require-clean`: PASS, four checksums clean.
- Ruff lint/format expanded gradual CI scope: PASS.
- mypy: PASS (33 source files).
- Frontend type/syntax and shell syntax: PASS.
- Python 3.10 runtime: NOT RUN locally; retained in GitHub Actions.

Combined unit + PostgreSQL coverage for new 1D modules: **85%** (241 statements, 37 missed). Device model 100%, repository 93%, service 86%, route 61%.

## Known Limitations

- Browser kiosks receive short-lived HttpOnly sessions; this does not claim hardware-backed key protection.
- Fleet management UI and remote commands remain Milestone 4C.
- Existing Kiosk service/repository callers still resolve Default Scope; explicit principal-to-scope propagation and unscoped-caller enforcement are Milestone 1E.
