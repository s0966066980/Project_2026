from fastapi.testclient import TestClient

from main import app
from services import emotion_service
from utils import auth_utils


def test_device_identity_receives_complete_admin_access():
    with TestClient(app) as client:
        response = client.get("/api/admin/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["access"] == "device_admin"
    assert body["principal"]["roles"] == ["device-admin"]
    assert body["principal"]["permissions"] == ["*"]
    assert body["principal"]["auth_method"] == "device_admin"
    assert body["principal"]["session_id"] is None


def test_password_authentication_surface_is_removed():
    requests = (
        ("get", "/api/admin/auth/ui-config", None),
        ("post", "/api/admin/auth/login", {"login_identity": "admin", "password": "secret"}),
        ("post", "/api/admin/auth/logout", None),
        ("post", "/api/admin/auth/rotate", None),
    )
    with TestClient(app) as client:
        responses = [getattr(client, method)(path, json=payload) if payload is not None else getattr(client, method)(path) for method, path, payload in requests]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]


def test_anonymous_browser_is_denied_when_device_security_is_enforced(monkeypatch):
    monkeypatch.setattr(auth_utils, "_security_enforced", lambda: True)

    with TestClient(app) as client:
        response = client.get("/api/admin/auth/me")

    assert response.status_code == 401


def test_kiosk_can_check_emotion_readiness_before_media_capture(monkeypatch):
    monkeypatch.setattr(
        emotion_service,
        "model_profiles",
        lambda: [{"id": "r1_omni", "ready": False, "status": "unavailable"}],
    )

    with TestClient(app) as client:
        response = client.get("/api/emotion/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "ready": False,
        "provider": {"id": "r1_omni", "ready": False, "status": "unavailable"},
    }
