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

Pending PostgreSQL isolation and relational-integrity test execution.

## GREEN

Pending implementation.

## Security Verification

Pending verification of no plaintext password/session token, safe authentication errors, production cookie attributes, server-resolved scope, and permission denial.

## Integration Verification

Pending PostgreSQL 1B → 1C upgrade, migration idempotency, tenant/store isolation, and full JSON compatibility regression.

## Known Limitations

- Milestone 1C provides only the necessary login/session bootstrap surface; broad Admin UI refactoring remains out of scope.
- Device identity and member UUID/PII migration remain later milestones.
