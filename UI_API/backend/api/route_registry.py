from dataclasses import dataclass
from typing import Any, Callable

import config
from routes import (
    admin_identity_routes,
    ai_push_routes,
    availability_routes,
    core_routes,
    checkout_confirmation_routes,
    debug_routes,
    demo_routes,
    device_identity_routes,
    emotion_routes,
    interaction_routes,
    member_routes,
    ordering_entry_routes,
    menu_routes,
    passive_voice_routes,
    push_copy_routes,
    realtime_routes,
    recommendation_event_routes,
    test_routes,
    v1_routes,
    voice_routes,
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


def _test_routes_enabled() -> bool:
    return _production_safe_flag("ENABLE_TEST_ROUTES", True)


def _debug_routes_enabled() -> bool:
    return _production_safe_flag("ENABLE_DEBUG_ROUTES", False)


ROUTE_REGISTRY: tuple[RouteRegistration, ...] = (
    RouteRegistration("public", v1_routes),
    RouteRegistration("public", admin_identity_routes),
    RouteRegistration("public", device_identity_routes),
    RouteRegistration("public", core_routes),
    RouteRegistration("public", checkout_confirmation_routes),
    RouteRegistration("public", menu_routes),
    RouteRegistration("admin", availability_routes),
    RouteRegistration("admin", push_copy_routes),
    RouteRegistration("ai", voice_routes),
    RouteRegistration("ai", ai_push_routes),
    RouteRegistration("ai", emotion_routes),
    RouteRegistration("public", interaction_routes),
    RouteRegistration("admin", recommendation_event_routes),
    RouteRegistration("public", realtime_routes),
    RouteRegistration("ai", passive_voice_routes),
    RouteRegistration("public", member_routes),
    RouteRegistration("public", ordering_entry_routes),
    RouteRegistration("dev", demo_routes, _demo_routes_enabled),
    RouteRegistration("dev", test_routes, _test_routes_enabled),
    RouteRegistration("dev", debug_routes, _debug_routes_enabled),
)


def iter_enabled_routes() -> tuple[RouteRegistration, ...]:
    return tuple(registration for registration in ROUTE_REGISTRY if registration.enabled())
