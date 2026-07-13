# Milestone 2A — API v1 Typed Contracts TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 2A.

- Authenticated Admin callers discover a stable `/api/v1` read surface before write migration.
- Generated clients receive explicit DTOs, pagination, timestamps, UUIDs, operation IDs and auth metadata.
- Validation/auth/server failures use one safe envelope with request correlation and no stack/SQL/secret.
- Existing `/api/*` callers continue unchanged through compatibility routes.

## Initial RED

Command: `pytest -q tests/test_api_v1_contracts.py`.

Result: **RED — 5 failed**. The failures prove the complete absence of `/api/v1` paths, typed envelopes, pagination validation, OpenAPI security/operation IDs, and v1 settings compatibility adapter while the legacy `/api/public_settings` route still passes.

## Boundary RED

Pending auth, scope, validation, OpenAPI uniqueness and legacy compatibility evidence.

## GREEN

Pending.

## Security Verification

Pending.

## Integration Verification

Pending.

## Known Limitations

- Milestone 2A migrates the caller-first read surface; write contracts remain on legacy compatibility APIs until their callers move.
