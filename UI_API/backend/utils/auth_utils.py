import secrets
import time

from fastapi import HTTPException, Request, UploadFile

import config

_RATE_BUCKETS: dict[tuple[str, str], list[float]] = {}


def _security_enforced() -> bool:
    return bool(config.get("SECURITY_ENFORCED", config.is_security_enforced()))


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return ""


def _constant_time_match(candidate: str, allowed: list[str]) -> bool:
    return bool(candidate) and any(
        secrets.compare_digest(candidate, token)
        for token in allowed
        if token
    )


def require_admin_token(request: Request):
    expected = str(config.get("ADMIN_API_TOKEN", "") or config.ADMIN_DEMO_TOKEN or "")
    if not _security_enforced() and not config.is_demo_public_mode():
        return
    token = (
        _bearer_token(request)
        or request.headers.get("X-Admin-Token")
        or request.query_params.get("token")
    )
    if not expected:
        raise HTTPException(status_code=503, detail="admin auth is not configured")
    if not token:
        raise HTTPException(status_code=401, detail="admin token required")
    if not _constant_time_match(token, [expected, config.ADMIN_DEMO_TOKEN]):
        raise HTTPException(status_code=403, detail="invalid admin token")


def require_kiosk_token(request: Request):
    expected = str(config.get("KIOSK_DEVICE_TOKEN", "") or config.POS_DEMO_TOKEN or "")
    if not _security_enforced() and not config.is_demo_public_mode():
        return
    token = (
        request.headers.get("X-Kiosk-Token")
        or request.headers.get("X-Pos-Token")
        or _bearer_token(request)
        or request.query_params.get("kiosk_token")
        or request.query_params.get("token")
    )
    if not expected:
        raise HTTPException(status_code=503, detail="kiosk auth is not configured")
    if not token:
        raise HTTPException(status_code=401, detail="kiosk token required")
    if not _constant_time_match(token, [expected, config.POS_DEMO_TOKEN]):
        raise HTTPException(status_code=403, detail="invalid kiosk token")


def websocket_token_allowed(client_type: str, token: str) -> bool:
    if not _security_enforced() and not config.is_demo_public_mode():
        return True
    if client_type == "admin":
        allowed = [str(config.get("ADMIN_API_TOKEN", "") or ""), config.ADMIN_DEMO_TOKEN, config.WS_DEMO_TOKEN]
    else:
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
    bucket_key = (scope, key or client_host)
    now = time.monotonic()
    cutoff = now - window_seconds
    hits = [hit for hit in _RATE_BUCKETS.get(bucket_key, []) if hit >= cutoff]
    if len(hits) >= resolved_limit:
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    hits.append(now)
    _RATE_BUCKETS[bucket_key] = hits


async def read_limited_upload(media: UploadFile, max_bytes: int | None = None) -> bytes:
    resolved_max = int(max_bytes or config.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    data = await media.read(resolved_max + 1)
    if len(data) > resolved_max:
        raise HTTPException(status_code=413, detail="upload too large")
    return data
