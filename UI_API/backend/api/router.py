import config
from core.async_utils import LoopBoundSemaphore
from models.dependencies import RouteDependencies
from routes import (
    ai_push_routes,
    core_routes,
    debug_routes,
    demo_routes,
    emotion_routes,
    interaction_routes,
    member_routes,
    menu_routes,
    passive_voice_routes,
    rag_routes,
    realtime_routes,
    test_routes,
    voice_routes,
)


def build_route_dependencies() -> dict:
    return RouteDependencies(ollama_semaphore=LoopBoundSemaphore(1)).as_dict()


def register_routes(app, deps: dict | None = None) -> dict:
    route_deps = deps or build_route_dependencies()

    app.include_router(core_routes.create_router(route_deps))
    app.include_router(menu_routes.create_router(route_deps))
    app.include_router(voice_routes.create_router(route_deps))
    app.include_router(rag_routes.create_router(route_deps))
    app.include_router(ai_push_routes.create_router(route_deps))
    app.include_router(emotion_routes.create_router(route_deps))
    app.include_router(interaction_routes.create_router(route_deps))
    app.include_router(realtime_routes.create_router(route_deps))
    app.include_router(demo_routes.create_router(route_deps))
    app.include_router(passive_voice_routes.create_router(route_deps))
    app.include_router(member_routes.create_router(route_deps))
    app.include_router(test_routes.create_router(route_deps))

    if config.get("ENABLE_DEBUG_ROUTES", False):
        app.include_router(debug_routes.create_router(route_deps))

    return route_deps
