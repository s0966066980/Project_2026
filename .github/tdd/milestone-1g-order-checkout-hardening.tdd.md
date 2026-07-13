# Milestone 1G — Order / Checkout Hardening TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1G.

- A Kiosk submits item IDs, quantities, options and promotion references; the server owns every price and total.
- Duplicate clicks and network retries with the same idempotency key return one Order result.
- Reusing a key for a different request is rejected without modifying the first Order.
- Order, item/pricing snapshots, promotion usage and outbox event commit atomically.
- Recommendation, emotion or AI telemetry failure cannot turn a valid checkout into a failed commercial transaction.

## Initial RED

Command: `pytest -q tests/test_order_checkout_hardening.py`.

Result: **RED — 5 failed**. The failures prove the missing Order state model, 0007 transactional schema, historical pricing snapshot, deterministic request fingerprint and shared idempotency conflict contract.

## Boundary RED

The initial PostgreSQL boundary test was written before 0007 apply and covered invalid direct completion, same-key fingerprint conflict, concurrent duplicate requests, a deliberately invalid item quantity, cross-tenant key reuse, historical snapshot mutation and cancellation outbox. The earlier security regression also required updating because the authoritative cart now intentionally contains additional immutable price fields.

## GREEN

- Order state, route/security, AI degradation and archive recovery targets: PASS (22 tests in final focused run).
- Documentation/commercial target matrix: PASS (33 tests in final static target run).
- Full JSON backend: PASS (250 tests).
- PostgreSQL 0001→0007 upgrade chain: PASS (7 integration tests).
- 1G integration: PASS for idempotent replay, fingerprint conflict, concurrency, rollback, scope isolation, historical snapshot, outcome and cancellation outbox.

## Security Verification

- Client price/total are ignored; catalog, option and promotion data are validated and priced server-side.
- Order, idempotency and transition queries enforce tenant/store/device ownership; raw `X-Tenant-ID` style headers are not used.
- Idempotency keys and canonical requests are persisted only as SHA-256 digests/fingerprints.
- Outbox payload contains opaque Order ID, status, currency and total; it contains no phone, credential or connection data.
- AI/recommendation/log/archive failure cannot roll back or change an already confirmed transaction result.

## Integration Verification

- Ruff affected scope: PASS.
- Ruff format affected/new scope: PASS.
- Mypy: PASS (39 source files).
- Python 3.12 application import: PASS. Python 3.10 runtime is retained in CI and was not locally available.
- Migration clean: PASS (0001–0007 checksum clean).
- Commercial scope and Member identity validators: PASS, zero violations.
- Frontend install/typecheck/syntax: PASS.
- Shell syntax and `git diff --check`: PASS.

## Known Limitations

- Payment provider integration is not part of Milestone 1G; `payment_pending`/`paid` are state contracts only.
- Worker consumption of the transactional outbox is deferred to Milestone 2E.
