import importlib

from fastapi import FastAPI


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi().get("paths", {}))


def _patch_route_config(monkeypatch, api_router, values):
    from api import route_registry

    def fake_config_get(key, default=None):
        return values.get(key, default)

    monkeypatch.setattr(route_registry.config, "get", fake_config_get)
    monkeypatch.setattr(route_registry.config, "is_production", lambda: bool(values.get("APP_ENV") == "production"))
    monkeypatch.setattr(route_registry.config, "ALLOW_UNSAFE_PRODUCTION_ROUTES", False)


def test_demo_and_test_routes_can_be_disabled(monkeypatch):
    from api import router as api_router
    importlib.reload(api_router)

    _patch_route_config(monkeypatch, api_router, {
        "ENABLE_DEMO_ROUTES": False,
        "ENABLE_TEST_ROUTES": False,
        "ENABLE_DEBUG_ROUTES": False,
    })
    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = _paths(app)

    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
    assert "/api/test/ask" not in paths
    assert "/api/ollama/models" not in paths


def test_demo_and_test_routes_remain_enabled_by_default(monkeypatch):
    from api import router as api_router
    importlib.reload(api_router)

    _patch_route_config(monkeypatch, api_router, {"ENABLE_DEBUG_ROUTES": False})

    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = _paths(app)

    assert "/api/demo/trigger_scenario" in paths
    assert "/api/test/ask" in paths
    assert "/api/ollama/models" in paths


def test_production_blocks_dev_routes_even_if_flags_are_true(monkeypatch):
    from api import router as api_router
    importlib.reload(api_router)

    _patch_route_config(monkeypatch, api_router, {
        "APP_ENV": "production",
        "ENABLE_DEMO_ROUTES": True,
        "ENABLE_TEST_ROUTES": True,
        "ENABLE_DEBUG_ROUTES": True,
    })
    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = _paths(app)

    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
    assert "/api/test/ask" not in paths
    assert "/api/ollama/models" not in paths
    assert "/api/debug/intervention_logs/{session_id}" not in paths
