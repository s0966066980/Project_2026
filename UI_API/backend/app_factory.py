import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from api.router import register_routes
from bootstrap.startup import background_init
from core.constants import FRONTEND_DIR, STATIC_CACHE_PREFIX, TUNNEL_ORIGIN_REGEX
from services import health_service, observability_service


@asynccontextmanager
async def lifespan(app):
    observability_service.apply_runtime_retention()
    await background_init()
    yield


def create_app() -> FastAPI:
    config.validate_startup_config()
    observability_service.configure_logging()
    app = FastAPI(title="Smart Ordering Kiosk API", version="9.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_origin_regex=None if config.is_production() else TUNNEL_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/live", include_in_schema=False)
    async def live():
        return {"status": "live"}

    @app.get("/ready", include_in_schema=False)
    async def ready():
        result = health_service.build_readiness()
        return JSONResponse(result, status_code=200 if result.get("ready") else 503)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
        if config.is_production() and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith(STATIC_CACHE_PREFIX):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    @app.middleware("http")
    async def structured_request_logging(request: Request, call_next):
        request_id = observability_service.safe_correlation_id(request.headers.get("X-Request-Id"), prefix="req")
        trace_id = observability_service.safe_correlation_id(request.headers.get("X-Trace-Id"), prefix="trace")
        token = observability_service.bind_correlation_context(request_id=request_id, trace_id=trace_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = int(response.status_code)
            response.headers["X-Request-Id"] = request_id
            response.headers["X-Trace-Id"] = trace_id
            return response
        finally:
            client = getattr(request, "client", None)
            commercial_scope = getattr(request.state, "commercial_scope", None)
            observability_service.log_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=observability_service.monotonic_ms(start),
                client_host=getattr(client, "host", "") if client else "",
                trace_id=trace_id,
                tenant_id=str(getattr(commercial_scope, "tenant_id", "") or ""),
                store_id=str(getattr(commercial_scope, "store_id", "") or ""),
                device_id=str(getattr(commercial_scope, "device_id", "") or ""),
            )
            observability_service.reset_correlation_context(token)

    register_routes(app)
    return app
