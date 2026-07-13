"""Failure policies for ephemeral shared infrastructure ports."""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

import config
from models.shared_infrastructure import DistributedLockLease
from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter


class SharedInfrastructureUnavailableError(RuntimeError):
    """A required shared-infrastructure operation could not be completed safely."""


@lru_cache(maxsize=1)
def _adapter() -> RedisSharedInfrastructureAdapter:
    url = str(config.get("REDIS_URL", "") or "").strip()
    if not url:
        raise SharedInfrastructureUnavailableError("Shared infrastructure is not configured")
    return RedisSharedInfrastructureAdapter.from_url(url)


def cache_get(tenant_id: UUID, store_id: UUID, resource: str) -> object | None:
    try:
        return _adapter().cache_get(tenant_id, store_id, resource)
    except Exception:
        return None


def cache_set(tenant_id: UUID, store_id: UUID, resource: str, value: object, ttl_seconds: int = 60) -> bool:
    try:
        _adapter().cache_set(tenant_id, store_id, resource, value, ttl_seconds)
        return True
    except Exception:
        return False


def allow_rate_limit(
    tenant_id: UUID,
    store_id: UUID,
    resource: str,
    *,
    limit: int,
    window_seconds: int,
) -> bool | None:
    try:
        return _adapter().allow_rate_limit(tenant_id, store_id, resource, limit=limit, window_seconds=window_seconds)
    except Exception as exc:
        if config.APP_ENV in {"staging", "production"}:
            raise SharedInfrastructureUnavailableError("Required rate-limit infrastructure is unavailable") from exc
        return None


def acquire_lock(
    tenant_id: UUID,
    store_id: UUID,
    resource: str,
    *,
    ttl_seconds: int = 30,
    required: bool = True,
) -> DistributedLockLease | None:
    try:
        return _adapter().acquire_lock(tenant_id, store_id, resource, ttl_seconds=ttl_seconds)
    except Exception as exc:
        if required:
            raise SharedInfrastructureUnavailableError("Required distributed lock is unavailable") from exc
        return None


def release_lock(lease: DistributedLockLease) -> bool:
    try:
        return _adapter().release_lock(lease.key, lease.token)
    except Exception:
        return False


def readiness() -> dict[str, str]:
    configured = bool(str(config.get("REDIS_URL", "") or "").strip())
    if not configured:
        return {
            "status": "failed" if config.APP_ENV in {"staging", "production"} else "skipped",
            "reason": "shared_infrastructure_not_configured",
        }
    try:
        return {"status": "ok"} if _adapter().ping() else {"status": "failed", "reason": "ping_failed"}
    except Exception:
        return {"status": "failed", "reason": "shared_infrastructure_unavailable"}
