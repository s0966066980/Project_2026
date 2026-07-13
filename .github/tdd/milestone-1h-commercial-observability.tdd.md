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

Pending log redaction, database/migration readiness, AI degraded mode, metric emission and documentation link gates.

## GREEN

Pending.

## Security Verification

Pending.

## Integration Verification

Pending.

## Known Limitations

- Pilot SLOs are targets, not measured historical attainment.
- External metrics/tracing backend and paging integration require deployment-owned infrastructure and are not fabricated locally.
- Passing the checklist does not mean “Production Certified”.
