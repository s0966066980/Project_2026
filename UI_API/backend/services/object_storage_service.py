"""Object storage adapters: local/dev and in-memory test. Production uses S3-compatible wiring."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID, uuid4

from models.object_storage import ObjectMetadata


class ObjectStorageError(ValueError):
    pass


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_ALLOWED_TYPES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "application/json",
        "audio/webm",
        "video/webm",
        "image/png",
        "image/jpeg",
    }
)
_MAX_BYTES = 20 * 1024 * 1024


def _normalize_filename(filename: str) -> str:
    name = Path(str(filename or "object.bin")).name
    name = _SAFE_NAME.sub("_", name).strip("._") or "object.bin"
    if ".." in name or name.startswith("/"):
        raise ObjectStorageError("invalid_filename")
    return name[:180]


@dataclass
class InMemoryObjectStorage:
    objects: dict[str, dict[str, Any]] = field(default_factory=dict)

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
    ) -> ObjectMetadata:
        if content_type not in _ALLOWED_TYPES:
            raise ObjectStorageError("content_type_not_allowed")
        if len(data) > _MAX_BYTES:
            raise ObjectStorageError("object_too_large")
        safe_name = _normalize_filename(filename)
        object_id = f"{tenant_id}/{uuid4().hex}_{safe_name}"
        checksum = hashlib.sha256(data).hexdigest()
        meta = ObjectMetadata(
            object_id=object_id,
            tenant_id=tenant_id,
            store_id=store_id,
            owner=owner,
            content_type=content_type,
            size=len(data),
            checksum=checksum,
            encryption="aes-256-gcm-envelope",
            retention_days=retention_days,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.objects[object_id] = {"meta": meta, "data": data, "deleted": False}
        return meta

    def get(self, object_id: str, *, tenant_id: UUID) -> bytes:
        row = self.objects.get(object_id)
        if row is None or row["deleted"]:
            raise ObjectStorageError("not_found")
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        return bytes(row["data"])

    def delete(self, object_id: str, *, tenant_id: UUID) -> bool:
        row = self.objects.get(object_id)
        if row is None:
            return False
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        row["deleted"] = True
        return True

    def signed_url(self, object_id: str, *, tenant_id: UUID, ttl_seconds: int = 300) -> str:
        row = self.objects.get(object_id)
        if row is None or row["deleted"]:
            raise ObjectStorageError("not_found")
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        expires = int(time.time()) + max(1, int(ttl_seconds))
        token = hashlib.sha256(f"{object_id}:{tenant_id}:{expires}".encode()).hexdigest()[:24]
        return f"https://objects.local/{quote(object_id)}?expires={expires}&token={token}"


_STORE = InMemoryObjectStorage()


def storage() -> InMemoryObjectStorage:
    return _STORE


def reset_for_tests() -> None:
    global _STORE
    _STORE = InMemoryObjectStorage()
