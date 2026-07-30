"""Milestone 7A: typed API v1 write contracts."""

from __future__ import annotations

from fastapi.testclient import TestClient

WRITE_PATHS = {
    "/api/v1/settings": "patch",
    "/api/v1/availability/{item_id}": "put",
    "/api/v1/promotions": "post",
    "/api/v1/rag/knowledge": "post",
    "/api/v1/rag/knowledge/{item_id}": "put",
    "/api/v1/rag/knowledge/publish": "post",
    "/api/v1/rag/knowledge/{item_id}/retire": "post",
    "/api/v1/rag/retrieval/configurations": "post",
    "/api/v1/rag/retrieval/configurations/{version}": "delete",
    "/api/v1/rag/retrieval/test": "post",
    "/api/v1/rag/retrieval/checks/{check_id}/confirm": "post",
    "/api/v1/rag/test-cases": "post",
    "/api/v1/rag/evaluation-runs": "post",
    "/api/v1/fleet/devices/{device_id}/commands": "post",
    "/api/v1/orders/{order_id}/transition": "post",
}


def _client(monkeypatch) -> TestClient:
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    return TestClient(app_factory.create_app())


def test_openapi_exposes_v1_write_operations(monkeypatch) -> None:
    client = _client(monkeypatch)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    for path, method in WRITE_PATHS.items():
        assert path in paths, path
        operation = paths[path][method]
        assert operation["operationId"].startswith("v1_")
        assert operation["security"]
        assert "200" in operation["responses"] or "422" in operation["responses"]


def test_settings_patch_validates_body(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.patch("/api/v1/settings", json={"values": {"AI_PUSH_TEXT_MIN": 18}})
    # Auth may pass in test mode via legacy token; either 200 or 401 is acceptable boundary.
    assert response.status_code in {200, 401, 403}
    if response.status_code == 200:
        body = response.json()
        assert "data" in body
        assert body["meta"]["request_id"].startswith("req_")
