from fastapi.testclient import TestClient

from main import app


def test_live_kiosk_and_admin_http_surfaces_are_available():
    with TestClient(app) as client:
        assert client.get("/live").status_code == 200
        assert client.get("/kiosk").status_code == 200
        assert client.get("/admin").status_code == 200

