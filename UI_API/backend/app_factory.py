from contextlib import asynccontextmanager
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from api.router import register_routes
from bootstrap.startup import background_init
from core.constants import FRONTEND_DIR, STATIC_CACHE_PREFIX, TUNNEL_ORIGIN_REGEX
from services import observability_service


@asynccontextmanager
async def lifespan(app):
    observability_service.apply_runtime_retention()
    await background_init()
    yield


def create_app() -> FastAPI:
    config.validate_startup_config()
    observability_service.configure_logging()
    app = FastAPI(title="Smart Kiosk POS API", version="9.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_origin_regex=None if config.is_production() else TUNNEL_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(STATIC_CACHE_PREFIX):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    @app.middleware("http")
    async def structured_request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or observability_service.new_request_id()
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            client = getattr(request, "client", None)
            observability_service.log_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=observability_service.monotonic_ms(start),
                client_host=getattr(client, "host", "") if client else "",
            )

    register_routes(app)
    return app
