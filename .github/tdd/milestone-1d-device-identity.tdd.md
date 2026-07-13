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

Pending PostgreSQL hierarchy, rotation overlap/cutover, revocation, and event integration.

## GREEN

Pending implementation.

## Security Verification

Pending no-plaintext, no URL credential, rate limit, audit/event, server scope, and production legacy flag verification.

## Integration Verification

Pending 0001→0004 apply/reapply/clean validation, full JSON compatibility, frontend, and shell gates.

## Known Limitations

- Browser kiosks receive short-lived HttpOnly sessions; this does not claim hardware-backed key protection.
- Fleet management UI and remote commands remain Milestone 4C.
