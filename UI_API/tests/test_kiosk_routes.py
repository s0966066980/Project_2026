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
