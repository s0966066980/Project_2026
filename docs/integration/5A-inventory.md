# Milestone 5A — Worker / Outbox Correctness Inventory

## Current caller

- `UI_API/backend/scripts/run_worker.py` — PostgreSQL worker process loop.
- `UI_API/backend/services/worker_service.py` — enqueue, claim, retry, DLQ, outbox delivery.
- `UI_API/backend/services/rag_governance_service.py` — enqueues `rag.rebuild` jobs.

## Current adapter (before 5A)

- PostgreSQL path in `run_worker.py` marked jobs succeeded without executing handlers.
- PostgreSQL path marked outbox rows published without sink ACK.
- Default in-memory handler returned no-op success for all `ALLOWED_JOB_TYPES`.

## Current persistence

- `background_jobs` and `order_outbox` in PostgreSQL (migrations 0007–0008).
- In-memory `InMemoryJobStore` for unit tests.

## Current fallback

- JSON analytics sink via `analytics_pipeline_service.publish` for order outbox events.
- Explicit DLQ for unknown handlers and missing side effects.

## Production path (target)

- `JobHandlerRegistry` resolves a handler per `ALLOWED_JOB_TYPES`.
- `OutboxDeliveryRouter` routes `order_*` events to analytics sink; published only after ACK.
- `PostgresJobStore` bridges `worker_service` to `worker_job_repository`.
- `run_worker.py` bootstraps production handlers and validates registry completeness.

## Compatibility path

- In-memory store and test-only `set_outbox_delivery_handler` remain for unit tests.
- JSON analytics sink retained as interim sink (not claimed as external analytics completion).

## Test path

- `UI_API/tests/test_worker_production_path.py`
- `UI_API/tests/postgres_worker_production_path_integration.py`
- Existing `test_worker_reliable_jobs.py` updated for side-effect contract.

## Known gaps

- `ai.background` intentionally fails until LLM gateway production cutover (5C).
- Full RAG rebuild indexing remains milestone 6A; handler records governed rebuild side effect only.
- External warehouse/POS sinks deferred to later milestones.