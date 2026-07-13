"""Milestone 2D shared Redis infrastructure contracts."""

from __future__ import annotations

from uuid import UUID

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def incr(self, key):
        self.operations.append(("incr", key))
        return self

    def ttl(self, key):
        self.operations.append(("ttl", key))
        return self

    def execute(self):
        values = []
        for operation, key in self.operations:
            if operation == "incr":
                self.client.values[key] = int(self.client.values.get(key, 0)) + 1
                values.append(self.client.values[key])
            else:
                values.append(self.client.ttls.get(key, -1))
        return values


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def expire(self, key, ttl):
        self.ttls[key] = ttl
        return True

    def set(self, key, value, ex=None, px=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex if ex is not None else px
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def eval(self, _script, _count, key, token):
        if self.values.get(key) != token:
            return 0
        return self.delete(key)

    def ping(self):
        return True


def test_key_is_tenant_store_isolated_and_contains_no_pii() -> None:
    from repositories.redis_shared_adapter import build_redis_key

    phone = "0912345678"
    key_a = build_redis_key("rate", TENANT, STORE, phone)
    key_b = build_redis_key("rate", TENANT, UUID(int=9), phone)
    assert key_a.startswith(f"project2026:v1:{TENANT}:{STORE}:rate:")
    assert key_a != key_b
    assert phone not in key_a


def test_rate_limit_is_shared_across_adapter_instances_and_has_ttl() -> None:
    from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter

    client = FakeRedis()
    first = RedisSharedInfrastructureAdapter(client)
    second = RedisSharedInfrastructureAdapter(client)
    assert first.allow_rate_limit(TENANT, STORE, "login:actor", limit=2, window_seconds=60)
    assert second.allow_rate_limit(TENANT, STORE, "login:actor", limit=2, window_seconds=60)
    assert not first.allow_rate_limit(TENANT, STORE, "login:actor", limit=2, window_seconds=60)
    assert 60 in client.ttls.values()


def test_cache_round_trip_is_scoped_and_bounded_by_ttl() -> None:
    from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter

    client = FakeRedis()
    adapter = RedisSharedInfrastructureAdapter(client)
    adapter.cache_set(TENANT, STORE, "menu", {"items": ["safe"]}, ttl_seconds=30)
    assert adapter.cache_get(TENANT, STORE, "menu") == {"items": ["safe"]}
    assert adapter.cache_get(TENANT, UUID(int=9), "menu") is None
    assert 30 in client.ttls.values()


def test_cache_degrades_but_required_lock_fails_closed(monkeypatch) -> None:
    from services import shared_infrastructure_service

    class BrokenAdapter:
        def cache_get(self, *_args, **_kwargs):
            raise ConnectionError("redis unavailable at credential-bearing-url")

        def acquire_lock(self, *_args, **_kwargs):
            raise ConnectionError("redis unavailable at credential-bearing-url")

    monkeypatch.setattr(shared_infrastructure_service, "_adapter", lambda: BrokenAdapter())
    assert shared_infrastructure_service.cache_get(TENANT, STORE, "menu") is None
    with pytest.raises(shared_infrastructure_service.SharedInfrastructureUnavailableError) as raised:
        shared_infrastructure_service.acquire_lock(TENANT, STORE, "checkout", required=True)
    assert "credential-bearing-url" not in str(raised.value)


def test_lock_owner_token_prevents_cross_instance_release() -> None:
    from repositories.redis_shared_adapter import RedisSharedInfrastructureAdapter

    client = FakeRedis()
    first = RedisSharedInfrastructureAdapter(client)
    second = RedisSharedInfrastructureAdapter(client)
    lease = first.acquire_lock(TENANT, STORE, "rebuild", ttl_seconds=10)
    assert lease is not None
    assert second.acquire_lock(TENANT, STORE, "rebuild", ttl_seconds=10) is None
    assert not second.release_lock(lease.key, "wrong-token")
    assert first.release_lock(lease.key, lease.token)


def test_production_rate_limit_failure_is_fail_closed(monkeypatch) -> None:
    from services import shared_infrastructure_service

    class BrokenAdapter:
        def allow_rate_limit(self, *_args, **_kwargs):
            raise ConnectionError("secret redis endpoint")

    monkeypatch.setattr(shared_infrastructure_service.config, "APP_ENV", "production")
    monkeypatch.setattr(shared_infrastructure_service, "_adapter", lambda: BrokenAdapter())
    with pytest.raises(shared_infrastructure_service.SharedInfrastructureUnavailableError) as raised:
        shared_infrastructure_service.allow_rate_limit(TENANT, STORE, "login", limit=1, window_seconds=60)
    assert "secret redis endpoint" not in str(raised.value)
