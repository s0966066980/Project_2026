import os

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient


def _security_client(monkeypatch):
    from utils import auth_utils

    def fake_config_get(key, default=None):
        values = {
            "SECURITY_ENFORCED": True,
            "ADMIN_API_TOKEN": "admin-secret",
            "KIOSK_DEVICE_TOKEN": "kiosk-secret",
            "RATE_LIMIT_ENABLED": False,
            "MAX_UPLOAD_BYTES": 3,
        }
        return values.get(key, default)

    monkeypatch.setattr(auth_utils.config, "get", fake_config_get)
    monkeypatch.setattr(auth_utils.config, "is_demo_public_mode", lambda: False)

    app = FastAPI()

    @app.get("/admin-only")
    async def admin_only(request: Request):
        auth_utils.require_admin_token(request)
        return {"ok": True}

    @app.post("/kiosk-only")
    async def kiosk_only(request: Request):
        auth_utils.require_kiosk_token(request)
        return {"ok": True}

    @app.post("/upload")
    async def upload(media: UploadFile = File(...)):
        data = await auth_utils.read_limited_upload(media, max_bytes=3)
        return {"size": len(data)}

    return TestClient(app)


def test_admin_token_required_when_security_is_enforced(monkeypatch):
    client = _security_client(monkeypatch)

    assert client.get("/admin-only").status_code == 401
    assert client.get("/admin-only", headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert client.get("/admin-only", headers={"X-Admin-Token": "admin-secret"}).json() == {"ok": True}
    assert client.get("/admin-only", headers={"Authorization": "Bearer admin-secret"}).json() == {"ok": True}


def test_kiosk_token_required_when_security_is_enforced(monkeypatch):
    client = _security_client(monkeypatch)

    assert client.post("/kiosk-only").status_code == 401
    assert client.post("/kiosk-only", headers={"X-Kiosk-Token": "wrong"}).status_code == 403
    assert client.post("/kiosk-only", headers={"X-Kiosk-Token": "kiosk-secret"}).json() == {"ok": True}


def test_upload_size_limit_returns_413(monkeypatch):
    client = _security_client(monkeypatch)

    ok = client.post("/upload", files={"media": ("ok.webm", b"123", "audio/webm")})
    assert ok.status_code == 200
    assert ok.json() == {"size": 3}

    too_large = client.post("/upload", files={"media": ("large.webm", b"1234", "audio/webm")})
    assert too_large.status_code == 413


def test_runtime_paths_are_absolute():
    import config

    assert os.path.isabs(config.MENU_JSON_PATH)
    assert os.path.isabs(config.LEARNING_DATA_DIR)
    assert os.path.isabs(config.SETTINGS_JSON_PATH)
    assert os.path.isabs(config.RAG_DOCUMENTS_DIR)


def test_production_route_gating(monkeypatch):
    from api import router as api_router

    def fake_config_get(key, default=None):
        values = {
            "ENABLE_DEMO_ROUTES": False,
            "ENABLE_TEST_ROUTES": False,
            "ENABLE_DEBUG_ROUTES": False,
        }
        return values.get(key, default)

    monkeypatch.setattr(api_router.config, "get", fake_config_get)
    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
    assert "/api/test/ask" not in paths
    assert "/api/debug/intervention_logs/{session_id}" not in paths
