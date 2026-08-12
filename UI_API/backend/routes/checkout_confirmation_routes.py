import asyncio

from capabilities.identity_access import scope_from_device_principal
from capabilities.ordering import CartError, CheckoutError
from capabilities.ordering import checkout_runtime as runtime
from fastapi import APIRouter, HTTPException, Request

from utils.auth_utils import check_rate_limit, require_kiosk_token


def _scope(request):
    return scope_from_device_principal(require_kiosk_token(request))


def _raise(exc):
    status = 409 if exc.code in {"cart_revision_conflict", "idempotency_conflict", "cart_closed"} else 422
    raise HTTPException(status_code=status, detail={"code": exc.code, **exc.details}) from exc


def create_router(_deps=None, *, prefix: str = "/api"):
    router = APIRouter(prefix=prefix, tags=["checkout-confirmation"])

    @router.put("/cart/{session_id}")
    async def replace_cart(request: Request, session_id: str, body: dict):
        scope = _scope(request)
        check_rate_limit(request, "cart_mutation", limit=180, key=session_id)
        try:
            return await asyncio.to_thread(
                runtime.default_cart().replace,
                scope=scope,
                session_id=session_id,
                expected_revision=int(body.get("expected_revision") or 0),
                lines=body.get("lines") or [],
            )
        except CartError as exc:
            _raise(exc)

    @router.get("/cart/{session_id}")
    async def get_cart(request: Request, session_id: str):
        return await asyncio.to_thread(runtime.default_cart().get, scope=_scope(request), session_id=session_id)

    @router.post("/checkout/prepare")
    async def prepare(request: Request, body: dict):
        session_id = str(body.get("session_id") or "")
        scope = _scope(request)
        check_rate_limit(request, "checkout_prepare", limit=120, key=session_id)
        try:
            return await asyncio.to_thread(runtime.default_module().prepare, scope=scope, session_id=session_id)
        except (CheckoutError, CartError) as exc:
            _raise(exc)

    @router.post("/checkout/confirm")
    async def confirm(request: Request, body: dict):
        scope = _scope(request)
        quote_id = str(body.get("quote_id") or "")
        key = str(request.headers.get("Idempotency-Key") or "")
        check_rate_limit(request, "checkout_confirm", limit=120, key=quote_id)
        try:
            result = await asyncio.to_thread(
                runtime.default_module().confirm, scope=scope, quote_id=quote_id, idempotency_key=key
            )
            if result.get("type") == "confirmed" and not result.get("replayed"):
                asyncio.create_task(asyncio.to_thread(runtime.dispatch_outbox))
            return result
        except CheckoutError as exc:
            _raise(exc)

    @router.get("/checkout/outcome/{quote_id}")
    async def outcome(request: Request, quote_id: str, idempotency_key: str):
        try:
            return await asyncio.to_thread(
                runtime.default_module().outcome,
                scope=_scope(request),
                quote_id=quote_id,
                idempotency_key=idempotency_key,
            )
        except CheckoutError as exc:
            _raise(exc)

    return router
