"""Real Redis integration for shared ephemeral infrastructure."""

from __future__ import annotations

import os
from uuid import UUID

import pytest


def test_real_redis_multi_instance_ttl_scope_and_lock() -> None:
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        pytest.skip("REDIS_URL is not configured")
    import redis

    from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter

    client_a = redis.Redis.from_url(redis_url, decode_responses=True)
    client_b = redis.Redis.from_url(redis_url, decode_responses=True)
    client_a.flushdb()
    first = RedisSharedInfrastructureAdapter(client_a)
    second = RedisSharedInfrastructureAdapter(client_b)
    tenant = UUID("00000000-0000-4000-8000-000000000001")
    store_a = UUID("00000000-0000-4000-8000-000000000002")
    store_b = UUID("00000000-0000-4000-8000-000000000009")

    first.cache_set(tenant, store_a, "menu", {"version": 1}, 20)
    assert second.cache_get(tenant, store_a, "menu") == {"version": 1}
    assert second.cache_get(tenant, store_b, "menu") is None
    assert first.allow_rate_limit(tenant, store_a, "login", limit=1, window_seconds=20)
    assert not second.allow_rate_limit(tenant, store_a, "login", limit=1, window_seconds=20)
    lease = first.acquire_lock(tenant, store_a, "rebuild", ttl_seconds=20)
    assert lease is not None
    assert second.acquire_lock(tenant, store_a, "rebuild", ttl_seconds=20) is None
    assert second.release_lock(lease.key, lease.token)
