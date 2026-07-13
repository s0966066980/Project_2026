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

在 GREEN 前的同一 contract suite 明確要求 auth metadata、scope、validation、OpenAPI uniqueness 與 legacy compatibility；所有 v1 assertion 因 route 尚不存在而失敗。

## GREEN

Command: `pytest -q tests/test_api_v1_contracts.py`.

Result: **GREEN — 5 passed** after the typed DTO, v1 router, safe error handler and scoped read adapters were added.

## Security Verification

新增 auth failure safe-envelope 與 forged commercial-scope header regression。Credential 不回顯，scope 仍由 verified/default server principal 解析。

## Integration Verification

- Target/security/documentation matrix: **PASS — 27 passed**.
- PostgreSQL affected order-scope/readiness integrations: **PASS — 2 passed**.
- Full JSON backend: **PASS — 263 passed**.
- Ruff affected scope and Ruff format: **PASS**.
- mypy: **PASS — 45 source files**.
- Application import, migration checksum/clean state and commercial scope integrity: **PASS**.
- Frontend typecheck/syntax and shell syntax: **PASS**.
- Python 3.10 runtime: **NOT RUN locally** (runtime unavailable; retained in CI matrix).

## Known Limitations

- Milestone 2A migrates the caller-first read surface; write contracts remain on legacy compatibility APIs until their callers move.
