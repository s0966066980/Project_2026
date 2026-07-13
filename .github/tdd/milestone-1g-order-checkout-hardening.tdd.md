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

Pending invalid transition, idempotency conflict, transaction rollback, concurrency and scope isolation evidence.

## GREEN

Pending.

## Security Verification

Pending server pricing, scope ownership, safe fingerprints and no PII/secret outbox payload verification.

## Integration Verification

Pending.

## Known Limitations

- Payment provider integration is not part of Milestone 1G; `payment_pending`/`paid` are state contracts only.
- Worker consumption of the transactional outbox is deferred to Milestone 2E.
