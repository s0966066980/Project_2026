"""What the application is allowed to publish over HTTP.

The unversioned `/api/*` compatibility surface was withdrawn in full — 67 paths
to zero (ADR-0062). Nothing stopped it coming back one route module at a time,
which is how it accumulated the first time: each addition looked local and
reasonable, and the second published contract per capability was never a
decision anybody made.
"""

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from main import app

pytestmark = [pytest.mark.contract]

# Browser entry points and probes. They carry no version because they serve
# HTML or a liveness answer to a human or an orchestrator, not a contract to a
# client that has to keep working across releases.
UNVERSIONED_ALLOWED = {
    "/",
    "/admin",
    "/kiosk",
    "/pos",
    "/live",
    "/ready",
    "/static",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}

# Flag-gated development routes. They answer 404 in a commercial runtime and
# are deliberately not versioned: a version would imply a stability they must
# not have.
DEVELOPMENT_PREFIXES = ("/api/demo/", "/api/debug/", "/api/test/")


def _http_paths() -> set[str]:
    return {route.path for route in app.routes if isinstance(route, (APIRoute, APIWebSocketRoute))} | {
        route.path for route in app.routes if getattr(route, "path", "").startswith("/static")
    }


def test_live_kiosk_and_admin_http_surfaces_are_available():
    with TestClient(app) as client:
        assert client.get("/live").status_code == 200
        assert client.get("/kiosk").status_code == 200
        assert client.get("/admin").status_code == 200


def test_no_unversioned_api_path_is_published():
    """`/api/...` without `/v1` is a second contract for a capability that has one."""

    offenders = sorted(
        path
        for path in _http_paths()
        if path.startswith("/api/") and not path.startswith("/api/v1/") and not path.startswith(DEVELOPMENT_PREFIXES)
    )
    assert offenders == [], (
        "the unversioned compatibility surface is withdrawn (ADR-0062); "
        f"publish these under /api/v1 instead: {offenders}"
    )


def test_every_published_path_is_versioned_or_explicitly_exempt():
    """Catches a new unversioned surface that does not happen to start with /api."""

    unexpected = sorted(
        path
        for path in _http_paths()
        if not path.startswith("/api/v1/")
        and not path.startswith("/ws/")
        and not path.startswith(DEVELOPMENT_PREFIXES)
        and path not in UNVERSIONED_ALLOWED
    )
    assert unexpected == [], f"unversioned and unexempt: {unexpected}"


def test_the_versioned_surface_is_not_empty():
    """A rule over an empty set passes without proving anything."""

    versioned = {path for path in _http_paths() if path.startswith("/api/v1/")}
    assert len(versioned) > 50, f"only {len(versioned)} versioned paths; the surface rules are not being exercised"
