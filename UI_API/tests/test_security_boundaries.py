import os

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.testclient import TestClient
from tests.auth_test_support import ADMIN_SESSION_TOKEN, configure_admin_session


def _security_client(monkeypatch):
    from utils import auth_utils

    def fake_config_get(key, default=None):
        values = {
            "SECURITY_ENFORCED": True,
            "KIOSK_DEVICE_TOKEN": "kiosk-secret",
            "RATE_LIMIT_ENABLED": False,
            "MAX_UPLOAD_BYTES": 3,
        }
        return values.get(key, default)

    monkeypatch.setattr(auth_utils.config, "get", fake_config_get)
    monkeypatch.setattr(auth_utils.config, "is_demo_public_mode", lambda: False)
    configure_admin_session(monkeypatch)

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


def test_admin_session_is_the_only_admin_credential(monkeypatch):
    client = _security_client(monkeypatch)

    assert client.get("/admin-only").status_code == 401
    assert client.get("/admin-only", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/admin-only", headers={"X-Admin-Token": "admin-secret"}).status_code == 401
    assert client.get("/admin-only", headers={"Authorization": "Bearer admin-secret"}).status_code == 401
    assert client.get("/admin-only?token=admin-secret").status_code == 401
    client.cookies.set("admin_session", ADMIN_SESSION_TOKEN)
    assert client.get("/admin-only").json() == {"ok": True}


def _staff_client(monkeypatch):
    """與 _security_client 相同的強制安全設定，但改用 authorize_admin_request。"""
    from utils import auth_utils

    def fake_config_get(key, default=None):
        values = {
            "SECURITY_ENFORCED": True,
            "KIOSK_DEVICE_TOKEN": "kiosk-secret",
            "RATE_LIMIT_ENABLED": False,
        }
        return values.get(key, default)

    monkeypatch.setattr(auth_utils.config, "get", fake_config_get)
    monkeypatch.setattr(auth_utils.config, "is_demo_public_mode", lambda: False)
    monkeypatch.setattr(auth_utils.config, "is_production", lambda: False)
    configure_admin_session(monkeypatch)

    app = FastAPI()

    @app.get("/staff-permission")
    async def staff_permission(request: Request):
        principal = auth_utils.authorize_admin_request(request, "catalog.availability.read")
        return {"roles": list(principal.roles), "permissions": list(principal.permissions)}

    @app.get("/manager-permission")
    async def manager_permission(request: Request):
        auth_utils.authorize_admin_request(request, "settings.write")
        return {"ok": True}

    @app.get("/debug-permission")
    async def debug_permission(request: Request):
        auth_utils.authorize_admin_request(request, "system.debug")
        return {"ok": True}

    return TestClient(app)


def test_staff_identity_requires_a_device_credential(monkeypatch):
    """員工不需要主管密碼，但仍必須來自通過裝置認證的門市機器。"""
    client = _staff_client(monkeypatch)

    assert client.get("/staff-permission").status_code == 401

    body = client.get("/staff-permission", headers={"X-Kiosk-Token": "kiosk-secret"}).json()
    assert body["roles"] == ["local-staff"]
    assert set(body["permissions"]) == {
        "catalog.availability.read",
        "catalog.availability.write",
        "recommendations.effectiveness.read",
    }


def test_staff_identity_never_reaches_manager_capabilities(monkeypatch):
    """裝置憑證不得成為主管能力的替代品，診斷權限尤其不可暴露於員工模式。"""
    client = _staff_client(monkeypatch)
    device = {"X-Kiosk-Token": "kiosk-secret"}

    assert client.get("/manager-permission", headers=device).status_code == 401
    assert client.get("/debug-permission", headers=device).status_code == 401

    client.cookies.set("admin_session", ADMIN_SESSION_TOKEN)
    assert client.get("/manager-permission", headers=device).json() == {"ok": True}


def test_kiosk_token_required_when_security_is_enforced(monkeypatch):
    client = _security_client(monkeypatch)

    assert client.post("/kiosk-only").status_code == 401
    assert client.post("/kiosk-only", headers={"X-Kiosk-Token": "wrong"}).status_code == 403
    assert client.post("/kiosk-only", headers={"X-Kiosk-Token": "kiosk-secret"}).json() == {"ok": True}
    assert client.post("/kiosk-only?kiosk_token=kiosk-secret").status_code == 401


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
    from api import route_registry
    from api import router as api_router

    def fake_config_get(key, default=None):
        values = {
            "ENABLE_DEMO_ROUTES": False,
            "ENABLE_TEST_ROUTES": False,
            "ENABLE_DEBUG_ROUTES": False,
        }
        return values.get(key, default)

    monkeypatch.setattr(route_registry.config, "get", fake_config_get)
    monkeypatch.setattr(route_registry.config, "is_production", lambda: True)
    monkeypatch.setattr(route_registry.config, "ALLOW_UNSAFE_PRODUCTION_ROUTES", False)
    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = set(app.openapi().get("paths", {}))

    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
    assert "/api/test/ask" not in paths
    assert "/api/debug/intervention_logs/{session_id}" not in paths


def test_production_startup_rejects_wildcard_cors(monkeypatch):
    import config
    from backend import app_factory

    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "SECURITY_ENFORCED", True)
    monkeypatch.setattr(config, "KIOSK_DEVICE_TOKEN", "kiosk-secret")
    monkeypatch.setattr(config, "CORS_ORIGINS", ["*"])
    monkeypatch.setattr(config, "ALLOW_UNSAFE_PRODUCTION_ROUTES", False)
    monkeypatch.setattr(config, "ADMIN_LOCAL_MANAGER_AUTH_ENABLED", False)
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_TOPOLOGY", "ha")
    monkeypatch.setenv("DATABASE_URL_FILE", "")
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime@db.example/project?sslmode=verify-full")

    try:
        app_factory.create_app()
    except RuntimeError as exc:
        assert "CORS_ORIGINS" in str(exc)
    else:
        raise AssertionError("production startup should fail with wildcard CORS")


def test_production_startup_accepts_safe_config(monkeypatch):
    import config
    from backend import app_factory

    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "SECURITY_ENFORCED", True)
    monkeypatch.setattr(config, "KIOSK_DEVICE_TOKEN", "kiosk-secret")
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://example.com"])
    monkeypatch.setattr(config, "ALLOW_UNSAFE_PRODUCTION_ROUTES", False)
    monkeypatch.setattr(config, "ADMIN_LOCAL_MANAGER_AUTH_ENABLED", False)
    monkeypatch.setattr(config, "_env_bool", lambda name, default=False: False)
    monkeypatch.setenv("ADMIN_MEMBER_REF_SECRET", "member-ref-secret")
    monkeypatch.setenv("DEFAULT_TENANT_ID", "00000000-0000-4000-8000-000000000001")
    monkeypatch.setenv("DEFAULT_STORE_ID", "00000000-0000-4000-8000-000000000002")
    monkeypatch.setenv("DEFAULT_DEVICE_ID", "00000000-0000-4000-8000-000000000003")
    monkeypatch.delenv("MEMBER_STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_BACKEND", "postgresql")
    monkeypatch.setenv("DATABASE_TOPOLOGY", "ha")
    monkeypatch.setenv("DATABASE_URL_FILE", "")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://configured-by-secret-manager/project?sslmode=verify-full",
    )
    monkeypatch.setenv("OBJECT_STORAGE_SIGNING_SECRET", "object-storage-signing-secret")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")

    app = app_factory.create_app()
    paths = set(app.openapi().get("paths", {}))
    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
