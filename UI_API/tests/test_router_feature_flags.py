import importlib

from fastapi import FastAPI


def _paths(app: FastAPI) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_demo_and_test_routes_can_be_disabled(monkeypatch):
    from api import router as api_router
    importlib.reload(api_router)

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
    paths = _paths(app)

    assert "/api/public_settings" in paths
    assert "/api/demo/trigger_scenario" not in paths
    assert "/api/test/ask" not in paths
    assert "/api/ollama/models" not in paths


def test_demo_and_test_routes_remain_enabled_by_default(monkeypatch):
    from api import router as api_router
    importlib.reload(api_router)

    monkeypatch.setattr(
        api_router.config,
        "get",
        lambda key, default=None: False if key == "ENABLE_DEBUG_ROUTES" else default,
    )

    app = FastAPI()
    api_router.register_routes(app, deps={"ollama_semaphore": object()})
    paths = _paths(app)

    assert "/api/demo/trigger_scenario" in paths
    assert "/api/test/ask" in paths
    assert "/api/ollama/models" in paths
