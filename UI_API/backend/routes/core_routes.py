"""Browser entry points for the two product frontends.

Every `/api/*` handler this module used to carry was a second, unversioned
implementation of a surface `/api/v1` already owns; they were withdrawn when
the compatibility surface was collapsed. What remains is the page routes, which
have no version because they serve HTML to a browser, not a contract.
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse

from core.constants import FRONTEND_DIR


def create_router(deps: dict) -> APIRouter:
    router = APIRouter(tags=["core"])

    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    @router.get("/")
    async def serve_frontend():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/kiosk")
    async def serve_kiosk():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/pos")
    async def serve_legacy_pos():
        return FileResponse(f"{FRONTEND_DIR}/kiosk/index.html", headers=_NO_CACHE)

    @router.get("/admin")
    async def serve_admin():
        return FileResponse(f"{FRONTEND_DIR}/admin/admin.html", headers=_NO_CACHE)

    return router
