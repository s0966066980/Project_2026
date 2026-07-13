"""Redis adapter for ephemeral cache, rate-limit, and distributed-lock ports."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any
from uuid import UUID

from models.shared_infrastructure import DistributedLockLease

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


def build_redis_key(kind: str, tenant_id: UUID, store_id: UUID, resource: str) -> str:
    digest = hashlib.sha256(str(resource or "").encode("utf-8")).hexdigest()[:32]
    safe_kind = "".join(char for char in str(kind).lower() if char.isalnum() or char in "_-") or "resource"
    return f"project2026:v1:{tenant_id}:{store_id}:{safe_kind}:{digest}"


class RedisSharedInfrastructureAdapter:
    def __init__(self, client: Any):
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisSharedInfrastructureAdapter:
        import redis

        return cls(
            redis.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                health_check_interval=30,
            )
        )

    def ping(self) -> bool:
        return bool(self._client.ping())

    def cache_get(self, tenant_id: UUID, store_id: UUID, resource: str) -> object | None:
        value = self._client.get(build_redis_key("cache", tenant_id, store_id, resource))
        return json.loads(value) if value is not None else None

    def cache_set(self, tenant_id: UUID, store_id: UUID, resource: str, value: object, ttl_seconds: int) -> None:
        self._client.set(
            build_redis_key("cache", tenant_id, store_id, resource),
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            ex=max(1, min(int(ttl_seconds), 86_400)),
        )

    def allow_rate_limit(
        self,
        tenant_id: UUID,
        store_id: UUID,
        resource: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> bool:
        key = build_redis_key("rate", tenant_id, store_id, resource)
        count = int(self._client.pipeline(transaction=True).incr(key).execute()[0])
        if count == 1:
            self._client.expire(key, max(1, int(window_seconds)))
        return count <= max(1, int(limit))

    def acquire_lock(
        self,
        tenant_id: UUID,
        store_id: UUID,
        resource: str,
        *,
        ttl_seconds: int,
    ) -> DistributedLockLease | None:
        key = build_redis_key("lock", tenant_id, store_id, resource)
        token = secrets.token_urlsafe(24)
        acquired = self._client.set(key, token, px=max(1000, int(ttl_seconds) * 1000), nx=True)
        return DistributedLockLease(key, token) if acquired else None

    def release_lock(self, key: str, token: str) -> bool:
        return bool(self._client.eval(_RELEASE_SCRIPT, 1, key, token))
