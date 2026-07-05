from api.route_registry import iter_enabled_routes
from core.async_utils import LoopBoundSemaphore
from models.dependencies import RouteDependencies


def build_route_dependencies() -> dict:
    return RouteDependencies(ollama_semaphore=LoopBoundSemaphore(1)).as_dict()


def register_routes(app, deps: dict | None = None) -> dict:
    route_deps = deps or build_route_dependencies()

    for registration in iter_enabled_routes():
        app.include_router(registration.module.create_router(route_deps))

    return route_deps
