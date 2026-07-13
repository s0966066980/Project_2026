"""Milestone 1H observability, readiness, and pilot gate contracts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_structured_log_redacts_secrets_phone_and_database_url() -> None:
    from services.observability_service import JsonLogFormatter

    record = logging.LogRecord(
        "ui_api.checkout",
        logging.ERROR,
        __file__,
        1,
        "checkout failed phone=0912345678 token=secret DATABASE_URL=postgresql://user:pass@db/app",
        (),
        None,
    )
    record.request_id = "req_test"
    record.trace_id = "trace_test"
    record.tenant_id = "tenant-safe"
    record.store_id = "store-safe"
    record.device_id = "device-safe"
    record.error_code = "checkout_failed"
    payload = json.loads(JsonLogFormatter().format(record))
    serialized = json.dumps(payload)
    assert payload["module"] == "ui_api.checkout"
    assert payload["request_id"] == "req_test"
    assert payload["trace_id"] == "trace_test"
    assert payload["error_code"] == "checkout_failed"
    assert "0912345678" not in serialized
    assert "secret" not in serialized
    assert "postgresql://" not in serialized
    assert "[REDACTED]" in serialized


def test_metric_registry_emits_required_commercial_signals() -> None:
    from services import observability_service

    observability_service.reset_metrics_for_tests()
    observability_service.increment_metric("checkout_attempts_total", status="confirmed")
    observability_service.increment_metric("checkout_idempotency_replays_total", status="replayed")
    snapshot = observability_service.metrics_snapshot()
    assert snapshot["checkout_attempts_total"]["confirmed"] == 1
    assert snapshot["checkout_idempotency_replays_total"]["replayed"] == 1
    for name in (
        "http_requests_total",
        "websocket_connections_total",
        "postgres_operations_total",
        "migration_validation_failures_total",
        "auth_failures_total",
        "device_auth_failures_total",
        "llm_provider_requests_total",
        "emotion_evidence_total",
        "intervention_outcomes_total",
        "order_outbox_pending",
    ):
        assert name in snapshot


def test_readiness_requires_database_migrations_and_scope_but_not_ai(monkeypatch) -> None:
    from services import health_service

    monkeypatch.setattr(health_service.postgres_utils, "storage_backend", lambda: "postgres")
    monkeypatch.setattr(health_service, "_database_readiness", lambda: {"status": "ok"})
    monkeypatch.setattr(health_service, "_migration_readiness", lambda: {"status": "ok"})
    monkeypatch.setattr(health_service, "_scope_readiness", lambda: {"status": "ok"})
    ready = health_service.build_readiness()
    assert ready["ready"] is True
    assert "ai" not in ready["required_checks"]

    monkeypatch.setattr(
        health_service,
        "_migration_readiness",
        lambda: {"status": "failed", "error_code": "migration_not_clean"},
    )
    assert health_service.build_readiness()["ready"] is False


def test_live_and_ready_are_separate_public_operational_contracts(monkeypatch) -> None:
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    monkeypatch.setattr(app_factory.observability_service, "configure_logging", lambda: None)
    monkeypatch.setattr(app_factory.health_service, "build_readiness", lambda: {"ready": False, "status": "not_ready"})
    monkeypatch.setattr(app_factory, "register_routes", lambda _app: None)
    client = TestClient(app_factory.create_app())
    assert client.get("/live").json() == {"status": "live"}
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False


def test_pilot_operations_documents_cover_required_gates() -> None:
    required = {
        "docs/operations/PILOT_SLO.md": ("target", "not historical attainment"),
        "docs/operations/ALERTS.md": ("migration drift", "outbox backlog", "AI degraded"),
        "docs/operations/RUNBOOK.md": ("Checkout", "WebSocket", "Backup / Restore", "Incident"),
        "docs/operations/SECURITY_PRIVACY_CHECKLIST.md": ("PII", "CORS", "Retention", "Dependency"),
        "docs/operations/RELEASE_CHECKLIST.md": ("NOT Production Certified", "migration", "restore"),
    }
    for relative_path, fragments in required.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for fragment in fragments:
            assert fragment.lower() in text.lower(), (relative_path, fragment)
