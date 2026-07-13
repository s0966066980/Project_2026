"""Ports for ephemeral shared infrastructure; PostgreSQL remains business truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DistributedLockLease:
    key: str
    token: str


class CachePort(Protocol):
    def cache_get(self, tenant_id: UUID, store_id: UUID, resource: str) -> object | None: ...

    def cache_set(self, tenant_id: UUID, store_id: UUID, resource: str, value: object, ttl_seconds: int) -> None: ...


class RateLimitPort(Protocol):
    def allow_rate_limit(
        self, tenant_id: UUID, store_id: UUID, resource: str, *, limit: int, window_seconds: int
    ) -> bool: ...


class DistributedLockPort(Protocol):
    def acquire_lock(
        self, tenant_id: UUID, store_id: UUID, resource: str, *, ttl_seconds: int
    ) -> DistributedLockLease | None: ...

    def release_lock(self, key: str, token: str) -> bool: ...
