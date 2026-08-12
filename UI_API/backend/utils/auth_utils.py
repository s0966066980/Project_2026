import secrets
import threading
import time
from uuid import UUID

from fastapi import HTTPException, Request, UploadFile

import config
from capabilities.identity_access import (
    AdminAuthorizationError,
    authorize_admin_action,
    device_identity_service,
)
from models.admin_identity import AdminPrincipal
from modules.identity.application import scope_from_admin_principal, scope_from_device_principal
from modules.operations import _observability as observability_service
from services import shared_infrastructure_service
from utils.commercial_scope_config import resolve_commercial_scope

_RATE_BUCKETS: dict[tuple[str, str, str], list[float]] = {}
_RATE_LOCK = threading.Lock()
_LAST_RATE_CLEANUP = 0.0


def _security_enforced() -> bool:
    return bool(config.get("SECURITY_ENFORCED", config.is_security_enforced()))


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return ""


def _constant_time_match(candidate: str, allowed: list[str]) -> bool:
    return bool(candidate) and any(secrets.compare_digest(candidate, token) for token in allowed if token)


def device_admin_principal(request: Request) -> AdminPrincipal:
    """Issue complete store-scoped Admin access from a verified device identity."""

    device_principal = require_kiosk_token(request)
    scope = scope_from_device_principal(device_principal)
    principal = AdminPrincipal(
        user_id=UUID(str(device_principal.device_id)),
        tenant_id=UUID(str(scope.tenant_id)),
        allowed_store_ids=(UUID(str(scope.store_id)),),
        roles=("device-admin",),
        permissions=("*",),
        session_id=None,
        auth_method="device_admin",
    )
    request.state.admin_principal = principal
    request.state.device_principal = device_principal
    return principal


def require_permission(permission: str):
    def dependency(request: Request):
        principal = device_admin_principal(request)
        try:
            return authorize_admin_action(principal, permission, scope_from_admin_principal(principal))
        except AdminAuthorizationError as exc:
            observability_service.increment_metric("auth_failures_total", status="permission_denied")
            raise HTTPException(status_code=403, detail="admin action is not allowed") from exc

    return dependency


def authorize_admin_request(request: Request, permission: str):
    """Authenticate a device-backed Admin and enforce the requested permission."""

    return require_permission(permission)(request)


def require_kiosk_token(request: Request):
    expected = str(config.get("KIOSK_DEVICE_TOKEN", "") or config.POS_DEMO_TOKEN or "")
    if not _security_enforced() and not config.is_demo_public_mode():
        development_principal = device_identity_service.legacy_device_principal(
            resolve_commercial_scope(request.headers)
        )
        request.state.device_principal = development_principal
        return development_principal
    cookie_name = str(config.get("DEVICE_SESSION_COOKIE_NAME", "kiosk_device_session"))
    session_principal = device_identity_service.authenticate_device_session(request.cookies.get(cookie_name, ""))
    if session_principal is not None:
        if request.headers.get("X-App-Version"):
            device_identity_service.touch_device_principal(session_principal, request.headers.get("X-App-Version", ""))
        request.state.device_principal = session_principal
        return session_principal
    token = request.headers.get("X-Kiosk-Token") or request.headers.get("X-Pos-Token") or _bearer_token(request)
    if not token:
        observability_service.increment_metric("device_auth_failures_total", status="missing")
        raise HTTPException(status_code=401, detail="device authentication required")
    if not bool(config.get("ENABLE_LEGACY_KIOSK_TOKEN", not config.is_production())):
        observability_service.increment_metric("device_auth_failures_total", status="legacy_disabled")
        raise HTTPException(status_code=403, detail="legacy Kiosk token is disabled")
    if not expected:
        observability_service.increment_metric("device_auth_failures_total", status="not_configured")
        raise HTTPException(status_code=503, detail="legacy Kiosk auth is not configured")
    if not _constant_time_match(token, [expected, config.POS_DEMO_TOKEN]):
        observability_service.increment_metric("device_auth_failures_total", status="invalid")
        raise HTTPException(status_code=403, detail="invalid kiosk token")
    principal = device_identity_service.legacy_device_principal(resolve_commercial_scope(request.headers))
    device_identity_service.record_legacy_device_use(resolve_commercial_scope(request.headers))
    request.state.device_principal = principal
    return principal


def websocket_token_allowed(client_type: str, token: str) -> bool:
    if not _security_enforced() and not config.is_demo_public_mode():
        return True
    if not bool(config.get("ENABLE_LEGACY_KIOSK_TOKEN", not config.is_production())):
        return False
    allowed = [str(config.get("KIOSK_DEVICE_TOKEN", "") or ""), config.POS_DEMO_TOKEN, config.WS_DEMO_TOKEN]
    return _constant_time_match(token, allowed)


def check_rate_limit(
    request: Request,
    scope: str,
    limit: int | None = None,
    window_seconds: int = 60,
    key: str | None = None,
) -> None:
    if not bool(config.get("RATE_LIMIT_ENABLED", True)):
        return
    resolved_limit = int(limit or config.get("RATE_LIMIT_DEFAULT_PER_MINUTE", 120) or 120)
    if resolved_limit <= 0:
        return
    client_host = request.client.host if request.client else "unknown"
    subject = str(key or client_host)
    use_shared = bool(config.get("SHARED_RATE_LIMIT_ENABLED", False)) or config.APP_ENV in {"staging", "production"}
    if use_shared:
        scope_context = resolve_commercial_scope()
        resources = [f"ip:{scope}:{client_host}"]
        if subject != client_host:
            resources.append(f"subject:{scope}:{subject}")
        try:
            shared_results = [
                shared_infrastructure_service.allow_rate_limit(
                    scope_context.tenant_id,
                    scope_context.store_id,
                    resource,
                    limit=resolved_limit,
                    window_seconds=window_seconds,
                )
                for resource in resources
            ]
        except shared_infrastructure_service.SharedInfrastructureUnavailableError as exc:
            raise HTTPException(status_code=503, detail="security rate limit is unavailable") from exc
        if any(result is False for result in shared_results):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        if all(result is True for result in shared_results):
            return
    now = time.monotonic()
    cutoff = now - window_seconds
    bucket_keys = [("ip", scope, client_host)]
    if subject != client_host:
        bucket_keys.append(("subject", scope, subject))

    global _LAST_RATE_CLEANUP
    with _RATE_LOCK:
        cleanup_interval = max(1, int(config.get("RATE_LIMIT_CLEANUP_INTERVAL_SEC", 60) or 60))
        max_buckets = max(100, int(config.get("RATE_LIMIT_MAX_BUCKETS", 10_000) or 10_000))
        if now - _LAST_RATE_CLEANUP >= cleanup_interval or len(_RATE_BUCKETS) >= max_buckets:
            stale_keys = [
                bucket_key
                for bucket_key, bucket_hits in _RATE_BUCKETS.items()
                if not bucket_hits or bucket_hits[-1] < cutoff
            ]
            for bucket_key in stale_keys:
                _RATE_BUCKETS.pop(bucket_key, None)
            if len(_RATE_BUCKETS) >= max_buckets:
                oldest_keys = sorted(
                    _RATE_BUCKETS,
                    key=lambda bucket_key: _RATE_BUCKETS[bucket_key][-1] if _RATE_BUCKETS[bucket_key] else 0,
                )[: len(_RATE_BUCKETS) - max_buckets + 1]
                for bucket_key in oldest_keys:
                    _RATE_BUCKETS.pop(bucket_key, None)
            _LAST_RATE_CLEANUP = now

        resolved_hits = {
            bucket_key: [hit for hit in _RATE_BUCKETS.get(bucket_key, []) if hit >= cutoff]
            for bucket_key in bucket_keys
        }
        if any(len(hits) >= resolved_limit for hits in resolved_hits.values()):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        for bucket_key, hits in resolved_hits.items():
            hits.append(now)
            _RATE_BUCKETS[bucket_key] = hits


async def read_limited_upload(media: UploadFile, max_bytes: int | None = None) -> bytes:
    resolved_max = int(max_bytes or config.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    data = await media.read(resolved_max + 1)
    if len(data) > resolved_max:
        raise HTTPException(status_code=413, detail="upload too large")
    return data
