from dataclasses import dataclass
from typing import Any, Callable

import config
from routes import (
    core_routes,
    debug_routes,
    demo_routes,
    realtime_routes,
    v1_admin_health_routes,
    v1_admin_operations_routes,
    v1_ai_push_routes,
    v1_campaign_routes,
    v1_catalog_routes,
    v1_context_routes,
    v1_device_identity_routes,
    v1_diagnostic_routes,
    v1_emotion_routes,
    v1_fleet_routes,
    v1_interaction_routes,
    v1_knowledge_routes,
    v1_member_routes,
    v1_operations_routes,
    v1_optimization_lab_routes,
    v1_ordering_routes,
    v1_project_brain_routes,
    v1_promotion_banner_routes,
    v1_push_copy_routes,
    v1_recommendation_event_routes,
    v1_voice_routes,
)


@dataclass(frozen=True)
class RouteRegistration:
    group: str
    # Route modules are loaded dynamically and expose create_router at module level.
    module: Any
    enabled: Callable[[], bool] = lambda: True


def _production_safe_flag(key: str, default: bool) -> bool:
    if config.is_production() and not config.ALLOW_UNSAFE_PRODUCTION_ROUTES:
        return False
    return bool(config.get(key, default))


def _demo_routes_enabled() -> bool:
    return _production_safe_flag("ENABLE_DEMO_ROUTES", True)


def _diagnostic_routes_enabled() -> bool:
    return _production_safe_flag("ENABLE_DIAGNOSTIC_ROUTES", True)


def _debug_routes_enabled() -> bool:
    return _production_safe_flag("ENABLE_DEBUG_ROUTES", False)


# One mounted surface per capability. The unversioned `/api/*` twins that used
# to sit beside these were withdrawn: the modules they came from are still the
# implementation, reached through the `v1_*` transport above them, so nothing
# here is a rewrite — only the second published prefix is gone.
ROUTE_REGISTRY: tuple[RouteRegistration, ...] = (
    RouteRegistration("public", v1_context_routes),
    RouteRegistration("public", v1_campaign_routes),
    RouteRegistration("public", v1_operations_routes),
    RouteRegistration("admin", v1_admin_operations_routes),
    RouteRegistration("admin", v1_admin_health_routes),
    RouteRegistration("public", v1_knowledge_routes),
    RouteRegistration("public", v1_fleet_routes),
    RouteRegistration("public", v1_ordering_routes),
    RouteRegistration("public", v1_member_routes),
    RouteRegistration("public", v1_device_identity_routes),
    RouteRegistration("public", v1_promotion_banner_routes),
    RouteRegistration("public", v1_interaction_routes),
    RouteRegistration("public", v1_recommendation_event_routes),
    RouteRegistration("ai", v1_ai_push_routes),
    RouteRegistration("ai", v1_voice_routes),
    RouteRegistration("ai", v1_emotion_routes),
    RouteRegistration("admin", v1_push_copy_routes),
    RouteRegistration("admin", v1_project_brain_routes),
    RouteRegistration("admin", v1_optimization_lab_routes),
    RouteRegistration("public", v1_catalog_routes),
    # Serves HTML pages and the WebSocket, neither of which carries a version.
    RouteRegistration("public", core_routes),
    RouteRegistration("public", realtime_routes),
    RouteRegistration("dev", demo_routes, _demo_routes_enabled),
    RouteRegistration("dev", v1_diagnostic_routes, _diagnostic_routes_enabled),
    RouteRegistration("dev", debug_routes, _debug_routes_enabled),
)


def iter_enabled_routes() -> tuple[RouteRegistration, ...]:
    return tuple(registration for registration in ROUTE_REGISTRY if registration.enabled())
