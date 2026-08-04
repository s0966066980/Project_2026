from routes.diagnostic_routes import create_router


def test_diagnostic_surface_has_explicit_paths_and_no_legacy_test_routes():
    paths = {route.path for route in create_router({}).routes}
    assert "/api/diagnostics/ask" in paths
    assert "/api/diagnostics/voice_prompt" in paths
    assert "/api/test/ask" not in paths
    assert "/api/test/voice_prompt" not in paths

