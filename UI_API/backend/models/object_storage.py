"""Object storage port contracts and truthful metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

# Encryption values must describe real adapter behavior only.
ENCRYPTION_NONE_TEST = "none-test"
ENCRYPTION_LOCAL_AES_GCM = "local-aes-gcm"
ENCRYPTION_PROVIDER_MANAGED = "provider-managed"
ENCRYPTION_KMS_ENVELOPE = "kms-envelope"

KNOWN_ENCRYPTION_MODES = frozenset(
    {
        ENCRYPTION_NONE_TEST,
        ENCRYPTION_LOCAL_AES_GCM,
        ENCRYPTION_PROVIDER_MANAGED,
        ENCRYPTION_KMS_ENVELOPE,
    }
)


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
    key_version: str = ""
    provider: str = "memory"
    bucket: str = ""
    provider_key: str = ""


class ObjectEncryptionPort(Protocol):
    """Encrypt/decrypt object bytes. Metadata must match the real mode."""

    @property
    def mode(self) -> str: ...

    @property
    def key_version(self) -> str: ...

    def encrypt(self, plaintext: bytes) -> bytes: ...

    def decrypt(self, ciphertext: bytes) -> bytes: ...


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

    def head(self, object_id: str, *, tenant_id: UUID) -> ObjectMetadata: ...

    def signed_url(
        self,
        object_id: str,
        *,
        tenant_id: UUID,
        ttl_seconds: int = 300,
        method: str = "GET",
    ) -> str: ...


class S3ObjectStoragePort(ObjectStoragePort, Protocol):
    """S3-compatible contract. Real cloud wiring requires external credentials."""

    def stream(self, object_id: str, *, tenant_id: UUID): ...

    def lifecycle_metadata(self, object_id: str, *, tenant_id: UUID) -> dict: ...
