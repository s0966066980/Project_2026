# Milestone 5A — Worker / Outbox Correctness (TDD)

## RED

- Unknown handler must not succeed (`test_unknown_handler_cannot_succeed`).
- Handler without `side_effect_id` must not succeed (`test_handler_without_side_effect_cannot_succeed`).
- Outbox must not publish until sink ACK (`test_outbox_not_published_until_sink_ack`).
- PostgreSQL worker cycle must execute handler and outbox router (`postgres_worker_production_path_integration`).

## GREEN

- `JobHandlerRegistry`, `worker_handlers`, `OutboxDeliveryRouter`, `PostgresJobStore`.
- `run_worker.py` uses `worker_service.run_worker_cycle` for PostgreSQL.

## Gate

Classification: `PRODUCTION_PATH_PASS` for worker handler execution and outbox ACK semantics.

Non-goals: real payment provider, cloud analytics warehouse, Kafka replacement.