"""Milestone 2A typed/versioned API contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.auth_test_support import authenticate_client, configure_admin_session, configure_device_session

V1_PATHS = {
    "/api/v1/auth/me",
    "/api/v1/commercial-context",
    "/api/v1/campaigns",
    "/api/v1/members",
    "/api/v1/orders",
    "/api/v1/promotions",
    "/api/v1/recommendations",
    "/api/v1/recommendation-effectiveness",
    "/api/v1/audits",
    "/api/v1/settings",
    "/api/v1/rag/studio",
    "/api/v1/rag/knowledge",
    "/api/v1/rag/retrieval/configurations",
    "/api/v1/rag/test-cases",
    "/api/v1/rag/evaluation-runs",
}


def _client(monkeypatch, *, authenticated: bool = True) -> TestClient:
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    if authenticated:
        configure_admin_session(monkeypatch)
        configure_device_session(monkeypatch)
    client = TestClient(app_factory.create_app())
    if authenticated:
        authenticate_client(client, admin=True, device=True)
    return client


def test_openapi_exposes_unique_typed_v1_operations_and_security(monkeypatch) -> None:
    client = _client(monkeypatch, authenticated=False)
    schema = client.get("/openapi.json").json()
    assert V1_PATHS <= set(schema["paths"])
    assert "/api/rag/reviews" not in schema["paths"]
    assert "/api/v1/rag/reviews" not in schema["paths"]
    assert "/api/v1/rag/test" not in schema["paths"]
    assert "/api/v1/rag/status" not in schema["paths"]
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


def test_v1_error_envelope_keeps_route_authored_detail(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.get("/api/v1/campaigns/does-not-exist")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "campaign_not_found"
    assert payload["error"]["message"] == "找不到活動。"


def test_v1_error_envelope_suppresses_internal_string_detail(monkeypatch) -> None:
    client = _client(monkeypatch, authenticated=False)
    response = client.get("/api/v1/campaigns", headers={"Authorization": "Bearer should-never-echo"})
    assert response.status_code in {401, 403}
    payload = response.json()
    assert payload["error"]["code"] in {"unauthorized", "forbidden"}
    assert payload["error"]["message"] in {"Authentication is required.", "The action is not allowed."}
    assert "should-never-echo" not in str(payload)


def test_v1_campaign_validation_errors_reach_the_client(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post("/api/v1/campaigns/publish", json={
        "name": "缺開始時間的活動",
        "objective": "promote_item",
        "audience": "all",
        "schedule": {"starts_at": "", "ends_at": "2026-08-31T22:00"},
        "promotion_rules": [{"type": "fixed_item_price", "item_ids": ["fries"], "promotion_price": 30}],
        "placements": ["menu_card"],
    })
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "campaign_invalid"
    assert any(item["path"] == "schedule.starts_at" for item in payload["error"]["details"])


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
    client = _client(monkeypatch, authenticated=False)
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


def test_legacy_api_contract_remains_available_to_authenticated_principals(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/api/public_settings").status_code == 200
    assert client.get("/api/v1/settings").status_code == 200


def test_v1_cart_quote_uses_authoritative_prices(monkeypatch) -> None:
    from services import checkout_pricing_service, promotion_service

    client = _client(monkeypatch)
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/cart/quote"]["post"]["operationId"] == "v1_quote_cart"
    # 結帳改讀 store-scoped 菜單主檔（ADR-0018），因此要 patch 這條路徑；
    # patch 舊的 get_menu 會失效並讓這個單元測試真的去查資料庫。
    monkeypatch.setattr(
        checkout_pricing_service.menu_repository,
        "get_menu_scoped",
        lambda scope=None, **_kwargs: [{"id": "meal", "name": "套餐", "category": "主餐", "price": 120}],
    )
    monkeypatch.setattr(
        checkout_pricing_service.menu_repository,
        "get_menu",
        lambda: [{"id": "meal", "name": "套餐", "category": "主餐", "price": 120}],
    )
    monkeypatch.setattr(promotion_service, "list_promotions", lambda _scope=None: [])
    response = client.post(
        "/api/v1/cart/quote",
        json={"cart_items": [{"id": "meal", "quantity": 2, "price": 1}]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["subtotal"] == 240
    assert data["total"] == 240
    assert data["items"][0]["base_unit_price"] == 120
    assert data["quote_version"] == "checkout-v1"
