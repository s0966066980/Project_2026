"""Regression tests for the production security hardening work."""

import importlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from tests.auth_test_support import authenticate_client, configure_admin_session

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _security_config(monkeypatch, config_module) -> None:
    values = {
        "SECURITY_ENFORCED": True,
        "RATE_LIMIT_ENABLED": True,
    }
    monkeypatch.setattr(config_module, "get", lambda key, default=None: values.get(key, default))
    monkeypatch.setattr(config_module, "is_demo_public_mode", lambda: False)


def test_session_stats_requires_admin_session(monkeypatch):
    import config
    from routes import core_routes

    _security_config(monkeypatch, config)
    monkeypatch.setattr(
        core_routes.log_repository,
        "get_session_logs",
        lambda: [{
            "session_id": "private-session",
            "final_cart_ids": ["MCD001"],
            "voice_turns": [{"user": "private transcript"}],
        }],
    )

    app = FastAPI()
    app.include_router(core_routes.create_router({}))
    client = TestClient(app)

    assert client.get("/api/session_stats").status_code == 401
    configure_admin_session(monkeypatch)
    authenticate_client(client)
    authorized = client.get("/api/session_stats")
    assert authorized.status_code == 200
    assert authorized.json()["sessions"][0]["session_id"] == "private-session"


def test_rag_status_requires_admin_read_permission(monkeypatch):
    import config
    from routes import rag_routes

    _security_config(monkeypatch, config)

    async def fake_health():
        return {
            "status": "ok",
            "chroma_path": "/private/chroma",
            "source_dir": "/private/sources",
            "selected_source_ids": ["private-source"],
        }

    monkeypatch.setattr(rag_routes.rag_document_service, "health_status", fake_health)
    app = FastAPI()
    app.include_router(rag_routes.create_router({}))
    client = TestClient(app)

    assert client.get("/api/rag/status").status_code == 401
    configure_admin_session(monkeypatch)
    authenticate_client(client)
    authorized = client.get("/api/rag/status")
    assert authorized.status_code == 200
    assert authorized.json()["chroma_path"] == "/private/chroma"


def test_rate_limit_cannot_be_bypassed_by_rotating_subject_keys(monkeypatch):
    from utils import auth_utils

    importlib.reload(auth_utils)
    monkeypatch.setattr(
        auth_utils.config,
        "get",
        lambda key, default=None: True if key == "RATE_LIMIT_ENABLED" else default,
    )
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/checkout",
        "headers": [],
        "client": ("203.0.113.10", 50000),
        "scheme": "https",
        "server": ("testserver", 443),
    })

    auth_utils.check_rate_limit(request, "checkout", limit=1, key="session-a")
    with pytest.raises(HTTPException) as exc:
        auth_utils.check_rate_limit(request, "checkout", limit=1, key="session-b")
    assert exc.value.status_code == 429


def test_menu_validation_rejects_attribute_injection_and_accepts_https_image():
    from services import menu_validation_service

    with pytest.raises(menu_validation_service.MenuValidationError):
        menu_validation_service.validate_menu_payload([{
            "id": "MCD001",
            "name": "Bad image",
            "category": "Test",
            "price": 100,
            "image": 'x" onerror="alert(1)',
        }])

    validated = menu_validation_service.validate_menu_payload([{
        "id": "MCD001",
        "name": "Valid item",
        "category": "Test",
        "price": 100,
        "image": "https://images.example.test/menu/item.png",
    }])
    assert validated[0]["image"].startswith("https://")


@pytest.fixture
def authoritative_cart(monkeypatch):
    from services import checkout_pricing_service

    menu = [
        {"id": "MCD001", "name": "Main", "category": "Meal", "price": 155},
        {"id": "MCD012", "name": "Fries", "category": "Side", "price": 45},
    ]
    monkeypatch.setattr(checkout_pricing_service.menu_repository, "get_menu", lambda: menu)
    monkeypatch.setattr(checkout_pricing_service.promotion_service, "list_promotions", lambda _scope=None: [])
    monkeypatch.setattr(checkout_pricing_service.promotion_service, "get_promotion", lambda _offer_id: None)
    return checkout_pricing_service


def test_checkout_ignores_client_price_and_recomputes_from_menu(authoritative_cart):
    priced = authoritative_cart.price_checkout_cart(
        [{"id": "MCD001", "quantity": 2, "price": 1}],
        ["MCD001"],
        is_member=False,
    )

    assert priced["total"] == 310
    assert priced["cart_items"][0] == {
        "id": "MCD001",
        "name": "Main",
        "category": "Meal",
        "price": 155,
        "quantity": 2,
        "base_unit_price": 155,
        "option_unit_total": 0,
        "discount_unit_total": 0,
        "final_unit_price": 155,
        "options": [],
    }
    assert priced["subtotal"] == 310
    assert priced["currency"] == "TWD"


def test_checkout_rejects_member_only_offer_for_guest(authoritative_cart, monkeypatch):
    monkeypatch.setattr(
        authoritative_cart.promotion_service,
        "get_promotion",
        lambda _offer_id: {
            "offer_id": "member-fries",
            "status": "active",
            "enabled": True,
            "member_only": True,
            "item_ids": ["MCD012"],
            "promo_price": 30,
        },
    )

    with pytest.raises(authoritative_cart.CartValidationError) as exc:
        authoritative_cart.price_checkout_cart(
            [{"id": "MCD012", "quantity": 1, "applied_offer_id": "member-fries"}],
            ["MCD012"],
            is_member=False,
        )
    assert exc.value.code == "member_required"


def test_checkout_enforces_required_cart_items(authoritative_cart, monkeypatch):
    monkeypatch.setattr(
        authoritative_cart.promotion_service,
        "get_promotion",
        lambda _offer_id: {
            "offer_id": "meal-fries",
            "status": "active",
            "enabled": True,
            "item_ids": ["MCD012"],
            "required_cart_item_ids": ["MCD001"],
            "promo_price": 30,
        },
    )

    with pytest.raises(authoritative_cart.CartValidationError) as exc:
        authoritative_cart.price_checkout_cart(
            [{"id": "MCD012", "quantity": 1, "applied_offer_id": "meal-fries"}],
            ["MCD012"],
            is_member=True,
        )
    assert exc.value.code == "promotion_requirements_not_met"


def test_pos_banner_preserves_member_only_eligibility(tmp_path, monkeypatch):
    from services import promotion_banner_service

    root = tmp_path / "promotions"
    root.mkdir()
    (root / "member.json").write_text(json.dumps({
        "id": "member-banner",
        "offer_id": "member-banner",
        "enabled": True,
        "surface": "pos_home_banner",
        "status": "active",
        "title": "Member special",
        "member_only": True,
        "item_ids": ["MCD012"],
        "promo_price": 30,
    }), encoding="utf-8")
    monkeypatch.setattr(promotion_banner_service.promotion_repository, "promotions_root", lambda: root)

    items = promotion_banner_service.get_active_pos_banners(
        now=datetime(2026, 7, 13, 12, 0, tzinfo=ZoneInfo("Asia/Taipei")),
    )
    assert items[0]["member_only"] is True


def test_admin_stats_request_sends_admin_credentials():
    source = (PROJECT_ROOT / "frontend/admin/admin.js").read_text(encoding="utf-8")
    assert "fetch(`${API}/api/session_stats`, { headers: adminHeaders() })" in source


def test_checkout_failure_is_not_converted_to_success():
    source = (PROJECT_ROOT / "frontend/kiosk/app.js").read_text(encoding="utf-8")
    assert "if (!res?.ok)" in source
    assert "throw error;" in source
    assert "orderCompleted = false;" in source


def test_menu_visuals_are_escaped_before_inner_html_rendering():
    menu_source = (
        PROJECT_ROOT / "frontend/kiosk/controllers/kioskMenuController.js"
    ).read_text(encoding="utf-8")
    kiosk_source = (PROJECT_ROOT / "frontend/kiosk/app.js").read_text(encoding="utf-8")

    assert 'src="${escapeHTML(visual.image)}"' in menu_source
    assert "${escapeHTML(visual.emoji)}" in menu_source
    assert 'src="${escapeHTML(visual.image)}"' in kiosk_source
    assert "parentElement.innerHTML" not in kiosk_source


def test_application_adds_security_headers(monkeypatch):
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    monkeypatch.setattr(app_factory.observability_service, "configure_logging", lambda: None)

    def register_probe(app):
        @app.get("/probe")
        async def probe():
            return {"ok": True}

    monkeypatch.setattr(app_factory, "register_routes", register_probe)
    response = TestClient(app_factory.create_app()).get("/probe")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_checkout_cutover_exposes_quote_identity_operations_only():
    from routes import checkout_confirmation_routes, core_routes

    legacy_paths = {route.path for route in core_routes.create_router({}).routes}
    checkout_paths = {route.path for route in checkout_confirmation_routes.create_router({}).routes}
    assert "/api/checkout" not in legacy_paths
    assert {"/api/checkout/prepare", "/api/checkout/confirm", "/api/checkout/outcome/{quote_id}"} <= checkout_paths


def test_tracked_settings_do_not_contain_credentials_or_fixed_secrets():
    import config

    settings = json.loads(
        (PROJECT_ROOT / "learning_data/settings.json").read_text(encoding="utf-8")
    )
    assert settings["DATABASE_URL"] == ""
    assert settings["ADMIN_MEMBER_REF_SECRET"] == ""
    assert config.DEFAULT_SETTINGS["ADMIN_MEMBER_REF_SECRET"] == ""
