"""Repository-side independence gates for the ten published capabilities.

These checks deliberately stop at the boundary that can be proven without a
customer database, target kiosk, or external provider.  They prevent a new
route from silently bypassing a capability surface while the deeper
PostgreSQL/restart/E2E evidence is collected per wave.
"""

import ast
from pathlib import Path

import pytest

from backend.api.route_registry import ROUTE_REGISTRY
from backend.capabilities import CAPABILITIES

pytestmark = [pytest.mark.architecture]
UI_API_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = UI_API_ROOT / "backend"
ROUTE_ROOT = BACKEND_ROOT / "routes"

_ROUTE_TO_CAPABILITY = {
    "v1_catalog_routes": "catalog",
    "core_routes": "operations_configuration",
    "realtime_routes": "voice",
    "v1_context_routes": "ordering",
    "v1_ordering_routes": "ordering",
    "v1_campaign_routes": "campaign_promotion",
    "v1_promotion_banner_routes": "campaign_promotion",
    "v1_operations_routes": "operations_configuration",
    "v1_admin_operations_routes": "operations_configuration",
    "v1_diagnostic_routes": "operations_configuration",
    "v1_push_copy_routes": "campaign_promotion",
    "v1_member_routes": "member",
    "v1_device_identity_routes": "identity_access",
    "v1_interaction_routes": "recommendation_analytics",
    "v1_recommendation_event_routes": "recommendation_analytics",
    "v1_ai_push_routes": "recommendation_analytics",
    "v1_knowledge_routes": "knowledge_rag",
    "v1_fleet_routes": "identity_access",
    "v1_voice_routes": "voice",
    "v1_emotion_routes": "emotion",
    "v1_admin_health_routes": "operations_configuration",
}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return values


def test_every_capability_has_an_explicit_route_owner() -> None:
    registered = {registration.module.__name__.rsplit(".", 1)[-1] for registration in ROUTE_REGISTRY}
    owners = {capability: [] for capability in (item.key for item in CAPABILITIES)}
    for route_name, capability in _ROUTE_TO_CAPABILITY.items():
        if route_name in registered:
            owners[capability].append(route_name)
    assert all(owners.values()), owners


def test_capability_routes_do_not_import_legacy_horizontal_implementations() -> None:
    violations: list[str] = []
    for path in ROUTE_ROOT.glob("*.py"):
        if path.stem in {"demo_routes", "diagnostic_routes", "debug_routes"}:
            continue
        for imported in _imports(path):
            if imported.startswith(("modules.", "repositories.")):
                violations.append(f"{path.name} -> {imported}")
    assert violations == []


def test_production_routes_have_no_legacy_service_or_repository_imports() -> None:
    development_only = {"demo_routes", "diagnostic_routes", "debug_routes"}
    violations: list[str] = []
    for path in ROUTE_ROOT.glob("*.py"):
        if path.stem in development_only:
            continue
        for imported in _imports(path):
            if imported.startswith(("modules.", "repositories.", "services.")) or imported in {
                "modules",
                "repositories",
                "services",
            }:
                violations.append(f"{path.name} -> {imported}")
    assert violations == []


def test_published_interfaces_have_stable_exports() -> None:
    missing: list[str] = []
    for capability in CAPABILITIES:
        package = BACKEND_ROOT / "capabilities" / capability.key
        source = (package / "interface.py").read_text(encoding="utf-8")
        if "__all__" not in source:
            missing.append(capability.key)
    assert missing == []


def test_obsolete_module_router_registry_is_removed() -> None:
    assert not (BACKEND_ROOT / "bootstrap" / "module_registry.py").exists()


def test_identity_horizontal_service_shims_are_removed() -> None:
    services_root = BACKEND_ROOT / "services"
    assert not (services_root / "admin_access_service.py").exists()
    assert not (services_root / "admin_identity_service.py").exists()


def test_admin_identity_transport_is_versioned_and_singular() -> None:
    """One published surface for "who is this Admin", not two.

    `admin_identity_routes.py` served `/api/admin/auth/me` with its own
    response shape while `/api/v1/auth/me` served another. Admin only ever
    called the versioned one, so the unversioned transport was withdrawn with
    the rest of the compatibility surface.
    """

    assert not (ROUTE_ROOT / "admin_identity_routes.py").exists()
    imports = _imports(ROUTE_ROOT / "v1_context_routes.py")
    assert "routes.v1_support" in imports


def test_realtime_transport_uses_the_published_operations_surface() -> None:
    imports = _imports(ROUTE_ROOT / "realtime_routes.py")
    assert "services" not in imports
    assert "capabilities.operations_configuration" in imports


def test_ai_push_transport_uses_the_published_recommendation_surface() -> None:
    imports = _imports(ROUTE_ROOT / "ai_push_routes.py")
    assert "services" not in imports
    assert "capabilities.recommendation_analytics" in imports


def test_monolithic_v1_route_module_is_removed() -> None:
    assert not (ROUTE_ROOT / "v1_routes.py").exists()
