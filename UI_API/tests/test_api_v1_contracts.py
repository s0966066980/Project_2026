"""Milestone 2A typed/versioned API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

V1_PATHS = {
    "/api/v1/auth/me",
    "/api/v1/commercial-context",
    "/api/v1/members",
    "/api/v1/orders",
    "/api/v1/promotions",
    "/api/v1/recommendations",
    "/api/v1/audits",
    "/api/v1/settings",
    "/api/v1/rag/reviews",
}


def _client(monkeypatch) -> TestClient:
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    return TestClient(app_factory.create_app())


def test_openapi_exposes_unique_typed_v1_operations_and_security(monkeypatch) -> None:
    client = _client(monkeypatch)
    schema = client.get("/openapi.json").json()
    assert V1_PATHS <= set(schema["paths"])
    operation_ids = []
    for path in V1_PATHS:
        operation = schema["paths"][path]["get"]
        operation_ids.append(operation["operationId"])
        assert operation["operationId"].startswith("v1_")
        assert operation["tags"]
        assert operation["security"]
        assert "200" in operation["responses"]
    assert len(operation_ids) == len(set(operation_ids))
    schemes = schema["components"]["securitySchemes"]
    assert "AdminSessionCookie" in schemes
    assert "BearerAuth" in schemes


def test_v1_me_and_context_use_typed_uuid_timestamp_envelope(monkeypatch) -> None:
    client = _client(monkeypatch)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["data"]["user_id"]
    assert body["data"]["tenant_id"]
    assert body["meta"]["request_id"].startswith("req_")
    assert body["meta"]["timestamp"].endswith("Z")

    context = client.get("/api/v1/commercial-context").json()
    assert context["data"]["tenant_id"] == body["data"]["tenant_id"]
    assert context["data"]["store_id"]


def test_v1_pagination_validation_uses_safe_error_envelope(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/api/v1/members?page=0&page_size=500")
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["request_id"]
    assert "traceback" not in str(payload).lower()
    assert "sql" not in str(payload).lower()


def test_v1_collection_contract_has_pagination_filter_and_sort(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/api/v1/members?page=1&page_size=10&sort_by=created_at&sort_order=desc&q=none")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["data"], list)
    assert payload["pagination"] == {
        "page": 1,
        "page_size": 10,
        "total": 0,
        "total_pages": 0,
    }


def test_v1_auth_failure_is_safe_and_does_not_echo_credentials(monkeypatch) -> None:
    from utils import auth_utils

    client = _client(monkeypatch)
    monkeypatch.setattr(auth_utils, "_security_enforced", lambda: True)
    original_get = auth_utils.config.get
    monkeypatch.setattr(
        auth_utils.config,
        "get",
        lambda key, default=None: "expected-token" if key == "ADMIN_API_TOKEN" else original_get(key, default),
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer should-never-echo"})
    assert response.status_code in {401, 403}
    payload = response.json()
    assert payload["error"]["code"] in {"unauthorized", "forbidden"}
    assert payload["meta"]["request_id"] == payload["error"]["request_id"]
    assert "should-never-echo" not in str(payload)


def test_v1_scope_ignores_unverified_commercial_headers(monkeypatch) -> None:
    client = _client(monkeypatch)
    expected = client.get("/api/v1/commercial-context").json()["data"]
    forged = client.get(
        "/api/v1/commercial-context",
        headers={
            "X-Tenant-ID": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "X-Store-ID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "X-Device-ID": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        },
    ).json()["data"]
    assert forged == expected


def test_legacy_api_contract_remains_available(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/api/public_settings").status_code == 200
    assert client.get("/api/v1/settings").status_code == 200
