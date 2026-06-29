from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config
from api.router import register_routes
from bootstrap.startup import background_init
from core.constants import FRONTEND_DIR, STATIC_CACHE_PREFIX, TUNNEL_ORIGIN_REGEX


@asynccontextmanager
async def lifespan(app):
    await background_init()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Smart Kiosk POS API", version="9.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_origin_regex=TUNNEL_ORIGIN_REGEX,
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

    register_routes(app)
    return app

