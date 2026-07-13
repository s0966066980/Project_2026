from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_kiosk_routes_serve_kiosk_frontend():
    from routes import core_routes

    app = FastAPI()
    app.include_router(core_routes.create_router({}))
    client = TestClient(app)

    for path in ("/", "/kiosk", "/pos"):
        response = client.get(path)
        assert response.status_code == 200
        assert "/static/kiosk/app.js" in response.text


def test_kiosk_pos_banner_route_returns_active_banners(monkeypatch):
    from routes import menu_routes

    app = FastAPI()
    app.include_router(menu_routes.create_router({}))
    client = TestClient(app)

    monkeypatch.setattr(
        menu_routes.promotion_banner_service,
        "get_pos_banner_response",
        lambda **kwargs: {"items": [{
            "id": "summer_combo_001",
            "badge": "限時優惠",
            "title": "夏日超值套餐",
            "subtitle": "雙層牛肉吉士堡 + 中薯 + 中可",
            "original_price": 189,
            "promo_price": 149,
            "rotation_seconds": 6,
        }],
        },
    )

    response = client.get("/api/promotions/pos-banner")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["id"] == "summer_combo_001"
    assert payload["items"][0]["promo_price"] == 149
