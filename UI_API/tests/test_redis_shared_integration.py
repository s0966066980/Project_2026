"""Shared cache, rate limit, scope, TTL and lock behaviour against a live Redis.

The CI job of the same name has pointed at this path since the file was removed in
06dd4b9, so the shared-infrastructure ports have been shipping unverified. These
cover the properties the ports exist to provide, not the Redis client itself:
tenant/store isolation, expiry, a window that actually closes, and a lock only its
holder can release.
"""

import os
import time
from uuid import uuid4

import pytest

from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter, build_redis_key

REDIS_URL = str(os.environ.get("REDIS_URL", "") or "").strip()

pytestmark = [
    pytest.mark.integration,
    pytest.mark.redis,
    pytest.mark.skipif(not REDIS_URL, reason="REDIS_URL is not configured"),
]


@pytest.fixture()
def adapter():
    instance = RedisSharedInfrastructureAdapter.from_url(REDIS_URL)
    if not instance.ping():
        pytest.fail("Redis did not answer ping")
    return instance


@pytest.fixture()
def scope():
    return uuid4(), uuid4()


def test_cache_round_trips_structured_values(adapter, scope):
    tenant_id, store_id = scope
    assert adapter.cache_get(tenant_id, store_id, "menu") is None

    adapter.cache_set(tenant_id, store_id, "menu", {"items": ["burger"], "count": 1}, 30)

    assert adapter.cache_get(tenant_id, store_id, "menu") == {"items": ["burger"], "count": 1}


def test_cache_is_isolated_between_stores(adapter, scope):
    tenant_id, store_id = scope
    other_store = uuid4()
    adapter.cache_set(tenant_id, store_id, "menu", "store-a", 30)

    assert adapter.cache_get(tenant_id, other_store, "menu") is None
    assert adapter.cache_get(uuid4(), store_id, "menu") is None


def test_cache_entries_expire(adapter, scope):
    tenant_id, store_id = scope
    adapter.cache_set(tenant_id, store_id, "short-lived", "value", 1)
    assert adapter.cache_get(tenant_id, store_id, "short-lived") == "value"

    time.sleep(1.5)

    assert adapter.cache_get(tenant_id, store_id, "short-lived") is None


def test_rate_limit_allows_up_to_the_limit_then_refuses(adapter, scope):
    tenant_id, store_id = scope
    allowed = [adapter.allow_rate_limit(tenant_id, store_id, "voice", limit=2, window_seconds=60) for _ in range(3)]

    assert allowed == [True, True, False]


def test_rate_limit_counts_each_store_separately(adapter, scope):
    tenant_id, store_id = scope
    other_store = uuid4()
    adapter.allow_rate_limit(tenant_id, store_id, "voice", limit=1, window_seconds=60)

    assert adapter.allow_rate_limit(tenant_id, store_id, "voice", limit=1, window_seconds=60) is False
    assert adapter.allow_rate_limit(tenant_id, other_store, "voice", limit=1, window_seconds=60) is True


def test_rate_limit_window_reopens(adapter, scope):
    tenant_id, store_id = scope
    assert adapter.allow_rate_limit(tenant_id, store_id, "checkout", limit=1, window_seconds=1) is True
    assert adapter.allow_rate_limit(tenant_id, store_id, "checkout", limit=1, window_seconds=1) is False

    time.sleep(1.5)

    assert adapter.allow_rate_limit(tenant_id, store_id, "checkout", limit=1, window_seconds=1) is True


def test_lock_is_exclusive_until_released(adapter, scope):
    tenant_id, store_id = scope
    lease = adapter.acquire_lock(tenant_id, store_id, "publish", ttl_seconds=30)
    assert lease is not None

    assert adapter.acquire_lock(tenant_id, store_id, "publish", ttl_seconds=30) is None

    assert adapter.release_lock(lease.key, lease.token) is True
    assert adapter.acquire_lock(tenant_id, store_id, "publish", ttl_seconds=30) is not None


def test_lock_release_requires_the_holders_token(adapter, scope):
    tenant_id, store_id = scope
    lease = adapter.acquire_lock(tenant_id, store_id, "publish", ttl_seconds=30)
    assert lease is not None

    assert adapter.release_lock(lease.key, "someone-elses-token") is False
    assert adapter.acquire_lock(tenant_id, store_id, "publish", ttl_seconds=30) is None


def test_keys_carry_the_scope_and_never_the_raw_resource(scope):
    tenant_id, store_id = scope
    key = build_redis_key("cache", tenant_id, store_id, "member/0912345678")

    assert key.startswith(f"project2026:v1:{tenant_id}:{store_id}:cache:")
    assert "0912345678" not in key
