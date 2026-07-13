# Milestone 1H — Commercial Observability / Production Gate TDD Evidence

## Source and User Journeys

Source: `CODEX_AUTONOMOUS_ROADMAP.txt`, Milestone 1H.

- Operators can distinguish process liveness from commercial readiness.
- Logs correlate HTTP, checkout, outbox and provider work without leaking PII or credentials.
- Metrics expose stable names for commercial and infrastructure failure signals.
- A pilot release is blocked by explicit configuration, migration, scope, security and recovery gates.

## Initial RED

Command: `pytest -q tests/test_commercial_observability.py`.

Result: **RED — 5 failed**. The failures prove missing safe correlated log fields/redaction, metric registry, database/migration/scope readiness contract, separate `/live` and `/ready` endpoints, and pilot SLO/alert/runbook/checklist documents.

## Boundary RED

The first real PostgreSQL readiness integration returned `not_ready` despite a valid hierarchy. It exposed an adapter bug that read fields directly from `CommercialScopeReadiness` instead of its typed `.scope`; the implementation was corrected before GREEN. The boundary suite also verifies DB unavailable fail-closed and that AI/RAG health is never invoked by basic readiness.

## GREEN

- Observability/security/readiness/documentation target matrix: PASS (78 tests).
- Full JSON backend: PASS (256 tests).
- PostgreSQL Order correlation and readiness integrations: PASS (2 tests).
- `/live` remains available while `/ready` returns 503 for required dependency failure.

## Security Verification

- Log formatter redacts phone, credential-like values and database URLs before serialization; exceptions expose type, not stack/data.
- Incoming request/trace IDs are syntax/length validated; client IP is masked.
- Tenant/store/device correlation comes only from verified server principal scope placed on request state, not untrusted scope headers.
- Idempotency keys remain hashed; transactional outbox correlation contains safe trace/Order fields and no session/PII.
- Public readiness omits database URL, exception detail and configured scope UUIDs.
- Production startup rejects JSON storage, missing database, disabled structured logging and non-positive retention.

## Integration Verification

- Ruff lint and format affected CI scope: PASS.
- Mypy: PASS (41 source files).
- Python 3.12 application import/route tests: PASS. Python 3.10 runtime remains in CI and was not locally available.
- Migration validate clean, commercial scope validator and Member identity verifier: PASS (zero violations).
- Frontend install/typecheck/syntax: PASS.
- Shell syntax and `git diff --check`: PASS.

## Known Limitations

- Pilot SLOs are targets, not measured historical attainment.
- External metrics/tracing backend and paging integration require deployment-owned infrastructure and are not fabricated locally.
- Passing the checklist does not mean “Production Certified”.
- In-process metrics reset on application restart; external durable telemetry/export remains a deployment milestone.
