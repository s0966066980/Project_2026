import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch):
    from routes import rag_routes
    from services import rag_alert_service
    importlib.reload(rag_alert_service)
    importlib.reload(rag_routes)
    monkeypatch.setattr(rag_routes, "authorize_admin_request", lambda request, permission: object())
    monkeypatch.setattr(rag_alert_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr(rag_alert_service.config, "get", lambda key, default=None: {
        "RAG_ALERT_MAX_RECORDS": 1000,
        "RAG_ALERT_WEBHOOK_ENABLED": False,
        "RATE_LIMIT_ENABLED": False,
    }.get(key, default))
    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    return TestClient(app), rag_alert_service


def test_rag_alert_routes_list_ack_and_resolve(tmp_path, monkeypatch):
    client, service = _client(tmp_path, monkeypatch)
    alert, _ = service.create_alert("rag_rebuild_validation_failed", message="validation failed")

    listed = client.get("/api/rag/alerts")
    assert listed.status_code == 200
    assert listed.json()["alerts"][0]["alert_id"] == alert["alert_id"]

    acknowledged = client.post(f"/api/rag/alerts/{alert['alert_id']}/ack")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["alert"]["status"] == "acknowledged"

    resolved = client.post(f"/api/rag/alerts/{alert['alert_id']}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["alert"]["status"] == "resolved"
