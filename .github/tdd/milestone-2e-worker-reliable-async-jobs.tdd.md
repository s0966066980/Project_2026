# Milestone 2E — Worker / Reliable Async Jobs TDD Evidence

## Source and Use Cases

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 2E.

- Durable job contract with scope, payload reference, attempts, idempotency and safe errors.
- Reliable queue: claim/visibility timeout, retry with backoff, dead-letter, cancellation.
- Consume Milestone 1G `order_outbox` with idempotent delivery and tenant isolation.
- Metrics: depth, oldest age, success/failure/retry/DLQ; API request path only enqueues.

## Initial RED

Command: `pytest -q tests/test_worker_reliable_jobs.py`.

Result: **RED** — missing migration `0008_worker_reliable_async_jobs.sql`, `models.worker_jobs`, and `services.worker_service`.

## GREEN

Target unit suite implements InMemory job/outbox store plus domain worker service. PostgreSQL migration `0008_worker_reliable_async_jobs.sql` and `worker_job_repository` provide durable queue/outbox claim path for production/CI.

Local verification:

- `pytest -q tests/test_worker_reliable_jobs.py` — **PASS (9)**
- Full JSON backend `pytest -q tests` — **PASS (278)**
- Ruff affected scope / format — **PASS**
- Mypy gradual (51 source files) — **PASS**
- PostgreSQL worker integration — **NOT RUN locally** (no authenticated local DATABASE_URL); retained in CI via `tests/postgres_worker_jobs_integration.py`

## Known Limitations

- Default outbox delivery is an in-process successful sink (metrics + published marker); external analytics/POS consumers arrive in later milestones.
- Large binary payloads stay as object references (Milestone 4B); payload_ref forbids secrets and credential-like keys.
