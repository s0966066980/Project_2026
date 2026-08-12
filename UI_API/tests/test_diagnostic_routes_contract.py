import pytest

import config
from app_factory import _api_documentation_urls
from routes.v1_diagnostic_routes import create_router

pytestmark = [pytest.mark.contract]


def test_diagnostic_surface_has_explicit_paths_and_no_legacy_test_routes():
    paths = {route.path for route in create_router({}).routes}
    assert "/api/v1/diagnostics/ask" in paths
    assert "/api/v1/diagnostics/voice-prompt" in paths
    assert "/api/v1/diagnostics/ollama-models" in paths
    assert "/api/test/ask" not in paths
    assert "/api/test/voice_prompt" not in paths


def test_commercial_runtime_does_not_serve_the_interactive_api_schema(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "pilot")

    assert _api_documentation_urls() == {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def test_development_runtime_keeps_the_interactive_api_schema(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "development")

    assert _api_documentation_urls() == {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }
