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


def test_kiosk_active_promotions_route_returns_valid_offers(monkeypatch):
    from routes import menu_routes

    app = FastAPI()
    app.include_router(menu_routes.create_router({}))
    client = TestClient(app)

    monkeypatch.setattr(
        menu_routes.menu_repository,
        "get_menu",
        lambda: [{"id": "MCD115", "name": "薯條", "price": 45, "category": "點心"}],
    )
    monkeypatch.setattr(
        menu_routes.rag_offer_service,
        "load_active_offers",
        lambda menu_items: [{
            "offer_id": "member_fries",
            "item_ids": ["MCD115"],
            "pricing": {"original_price": 45, "promotion_price": 30},
            "ad": {"headline": "會員限定", "copy": "主餐加購薯條只要 $30", "cta": "加入優惠"},
        }],
    )

    response = client.get("/api/promotions/active")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["total"] == 1
    assert payload["offers"][0]["pricing"]["promotion_price"] == 30
