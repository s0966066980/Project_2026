import asyncio
import json
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.auth_test_support import authenticate_client, configure_admin_session


def test_health_runtime_summary_reports_log_counts(tmp_path, monkeypatch):
    from services import health_service

    monkeypatch.setattr(health_service.observability_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        health_service.config,
        "get",
        lambda key, default=None: 30 if key == "LOG_RETENTION_DAYS" else default,
    )
    path = tmp_path / "recommendation_events.json"
    path.write_text(json.dumps([
        {"timestamp": "2026-07-04T00:00:00", "event_type": "recommendation_shown"},
    ]), encoding="utf-8")

    result = health_service._runtime_health()

    assert result["status"] == "ok"
    assert result["retention_days"] == 30
    assert any(row["name"] == "recommendation_events.json" and row["records"] == 1 for row in result["logs"])


def test_health_runtime_summary_marks_invalid_json_as_degraded(tmp_path, monkeypatch):
    from services import health_service

    monkeypatch.setattr(health_service.observability_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    (tmp_path / "session_logs.json").write_text("{bad json", encoding="utf-8")

    result = health_service._runtime_health()

    assert result["status"] == "degraded"
    assert result["warnings"]


def test_admin_health_route_requires_admin_session(monkeypatch):
    from routes import core_routes

    async def fake_health(_actions=None):
        return {
            "status": "ok",
            "generated_at": datetime.now().isoformat(),
            "app": {},
            "checks": {},
        }

    monkeypatch.setattr(core_routes.health_service, "build_admin_health", fake_health)
    monkeypatch.setattr(core_routes.admin_audit_service, "list_admin_audits", lambda limit, scope: [])
    app = FastAPI()
    app.include_router(core_routes.create_router({}))
    client = TestClient(app)

    assert client.get("/api/admin/health").status_code == 401
    configure_admin_session(monkeypatch)
    authenticate_client(client)
    ok = client.get("/api/admin/health")
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"


def test_admin_health_is_not_ready_when_required_check_fails(monkeypatch):
    from services import health_service

    monkeypatch.setattr(health_service, "_postgres_health", lambda: {"name": "postgres", "status": "ok"})
    monkeypatch.setattr(health_service, "_runtime_health", lambda: {"name": "runtime_logs", "status": "ok", "logs": []})
    monkeypatch.setattr(health_service, "_recommendation_health", lambda: {"name": "recommendation_events", "status": "ok"})
    monkeypatch.setattr(health_service, "_rag_alert_health", lambda: {"name": "rag_alerts", "status": "ok"})
    monkeypatch.setattr(health_service, "build_readiness", lambda: {
        "ready": False,
        "status": "not_ready",
        "required_checks": {"commercial_scope": {"status": "failed"}},
    })

    async def healthy_rag():
        return {"status": "ok"}

    monkeypatch.setattr(health_service.rag_document_service, "health_status", healthy_rag)

    result = asyncio.run(health_service.build_admin_health())

    assert result["status"] == "not_ready"
    assert result["readiness"]["ready"] is False
    assert result["operational"]["state"] == "unsafe_to_operate"
    assert result["operational"]["incidents"][0]["severity"] == "critical"


def test_operational_health_restores_acknowledged_incident_state():
    from services import health_service

    checks = {
        "recommendation_events": {"status": "degraded", "message": "events stale"},
        "rag": {"status": "ok"},
        "rag_alerts": {"status": "ok"},
    }
    readiness = {"ready": True, "required_checks": {"database": {"status": "ok"}}}
    first = health_service.build_operational_health(checks, readiness)
    incident_id = first["incidents"][0]["incident_id"]
    action = {
        "action": "health.incident.acknowledge",
        "target_type": "health_incident",
        "target_id": incident_id,
        "actor": "manager-1",
        "created_at": "2026-07-24T08:00:00+08:00",
    }

    result = health_service.build_operational_health(checks, readiness, [action])

    assert result["state"] == "operate_with_degraded_features"
    assert result["incidents"][0]["status"] == "acknowledged"
    assert result["incidents"][0]["last_actor"] == "manager-1"


def test_recommendation_health_requires_fresh_events(monkeypatch):
    from services import health_service

    monkeypatch.setattr(
        health_service.recommendation_event_repository,
        "get_recommendation_events",
        lambda limit=5000: [{"event_type": "recommendation_shown", "timestamp": "2020-01-01T00:00:00+00:00"}],
    )
    monkeypatch.setattr(
        health_service.config,
        "get",
        lambda key, default=None: 24 if key == "RECOMMENDATION_EVENT_FRESHNESS_HOURS" else default,
    )

    result = health_service._recommendation_health()

    assert result["status"] == "degraded"
    assert result["latest_event_at"] == "2020-01-01T00:00:00+00:00"
    assert result["freshness_hours"] == 24
