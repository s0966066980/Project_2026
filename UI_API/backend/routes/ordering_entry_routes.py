import asyncio

from fastapi import APIRouter, HTTPException, Request
from modules.ordering_entry import EntryFlowError, runtime

from services.commercial_context_service import scope_from_device_principal
from utils.auth_utils import check_rate_limit, require_kiosk_token


def _scope(r):
    return scope_from_device_principal(require_kiosk_token(r))


def _error(e):
    raise HTTPException(status_code=409 if "conflict" in e.code else 422, detail={"code": e.code, **e.details}) from e


def create_router(_deps=None):
    router = APIRouter(prefix="/api/entry-flow", tags=["ordering-entry"])

    @router.post("/start")
    async def start(request: Request, body: dict):
        scope = _scope(request)
        check_rate_limit(request, "entry_start", limit=30, key=str(scope.device_id))
        policy = body.get("policy") if isinstance(body.get("policy"), dict) else {"membership_enabled": True}
        try:
            return await asyncio.to_thread(
                runtime.default_module().start,
                scope=scope,
                policy_version=str(body.get("policy_version") or "runtime-v1"),
                policy=policy,
                entry_flow_id=str(body.get("entry_flow_id") or ""),
                policy_loaded=body.get("policy_loaded") is True,
            )
        except EntryFlowError as e:
            _error(e)

    @router.post("/{entry_flow_id}/command")
    async def command(request: Request, entry_flow_id: str, body: dict):
        try:
            return await asyncio.to_thread(
                runtime.default_module().command,
                scope=_scope(request),
                entry_flow_id=entry_flow_id,
                phase_revision=int(body.get("phase_revision") or 0),
                command=str(body.get("command") or ""),
                payload=body.get("payload") or {},
            )
        except EntryFlowError as e:
            _error(e)

    @router.get("/{entry_flow_id}")
    async def get(request: Request, entry_flow_id: str):
        try:
            return await asyncio.to_thread(
                runtime.default_module().get, scope=_scope(request), entry_flow_id=entry_flow_id
            )
        except EntryFlowError as e:
            _error(e)

    return router
