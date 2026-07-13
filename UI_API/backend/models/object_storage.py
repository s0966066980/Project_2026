"""Object storage port contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class ObjectMetadata:
    object_id: str
    tenant_id: UUID
    store_id: UUID | None
    owner: str
    content_type: str
    size: int
    checksum: str
    encryption: str
    retention_days: int
    created_at: str
    deleted_at: str = ""


class ObjectStoragePort(Protocol):
    def put(
        self,
        *,
        tenant_id: UUID,
        store_id: UUID | None,
        owner: str,
        content_type: str,
        data: bytes,
        filename: str,
        retention_days: int = 30,
    ) -> ObjectMetadata: ...

    def get(self, object_id: str, *, tenant_id: UUID) -> bytes: ...

    def delete(self, object_id: str, *, tenant_id: UUID) -> bool: ...

    def signed_url(self, object_id: str, *, tenant_id: UUID, ttl_seconds: int = 300) -> str: ...
