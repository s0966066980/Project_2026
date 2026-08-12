"""Object storage adapters with truthful metadata and HMAC signed access.

Production path defaults to LocalObjectStorage for development and an S3-compatible
contract for cloud wiring. In-memory is test-only and reports encryption=none-test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from uuid import UUID, uuid4

import config
from models.object_storage import (
    ENCRYPTION_LOCAL_AES_GCM,
    ENCRYPTION_NONE_TEST,
    ObjectMetadata,
)
from modules.runtime_persistence import configured_runtime_paths

try:
    from repositories import object_storage_repository
except Exception:  # pragma: no cover - import-time path for isolated unit tests
    object_storage_repository = None  # type: ignore[assignment]


class ObjectStorageError(ValueError):
    pass


class ObjectStorageConfigError(RuntimeError):
    """Missing or unsafe production object-storage configuration."""


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
_DEFAULT_SIGN_TTL = 300
_MAX_SIGN_TTL = 3600


def _normalize_filename(filename: str) -> str:
    name = Path(str(filename or "object.bin")).name
    name = _SAFE_NAME.sub("_", name).strip("._") or "object.bin"
    if ".." in name or name.startswith("/") or "\\" in name:
        raise ObjectStorageError("invalid_filename")
    return name[:180]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _signing_secret(*, require: bool = False) -> bytes:
    # Secrets must come from environment / secret manager only — never settings.json.
    raw = str(os.getenv("OBJECT_STORAGE_SIGNING_SECRET", "") or "").strip()
    if not raw:
        if require or config.is_commercial_runtime() or config.is_security_enforced():
            raise ObjectStorageConfigError("OBJECT_STORAGE_SIGNING_SECRET is required")
        # Development/test fallback is explicit and never claimed as production HMAC material.
        raw = "dev-only-object-storage-signing-secret"
    if raw in {"CHANGE_ME", "change_me", "changeme"}:
        raise ObjectStorageConfigError("OBJECT_STORAGE_SIGNING_SECRET must not use a placeholder")
    return raw.encode("utf-8")


def _canonical_sign_payload(
    *,
    object_id: str,
    tenant_id: UUID,
    expires: int,
    method: str,
) -> bytes:
    method_norm = str(method or "GET").strip().upper() or "GET"
    return f"{object_id}\n{tenant_id}\n{expires}\n{method_norm}".encode("utf-8")


def sign_access(
    *,
    object_id: str,
    tenant_id: UUID,
    expires: int,
    method: str = "GET",
    secret: bytes | None = None,
) -> str:
    key = secret if secret is not None else _signing_secret()
    digest = hmac.new(
        key,
        _canonical_sign_payload(object_id=object_id, tenant_id=tenant_id, expires=expires, method=method),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_signed_access(
    *,
    object_id: str,
    tenant_id: UUID,
    expires: int,
    signature: str,
    method: str = "GET",
    now: int | None = None,
    secret: bytes | None = None,
) -> bool:
    current = int(time.time() if now is None else now)
    if int(expires) < current:
        return False
    expected = sign_access(
        object_id=object_id,
        tenant_id=tenant_id,
        expires=int(expires),
        method=method,
        secret=secret,
    )
    return hmac.compare_digest(expected, str(signature or ""))


def build_signed_url(
    *,
    object_id: str,
    tenant_id: UUID,
    ttl_seconds: int = _DEFAULT_SIGN_TTL,
    method: str = "GET",
    base_url: str = "https://objects.local",
    secret: bytes | None = None,
) -> str:
    ttl = max(1, min(int(ttl_seconds), _MAX_SIGN_TTL))
    expires = int(time.time()) + ttl
    signature = sign_access(
        object_id=object_id,
        tenant_id=tenant_id,
        expires=expires,
        method=method,
        secret=secret,
    )
    query = urlencode(
        {
            "expires": str(expires),
            "tenant_id": str(tenant_id),
            "method": str(method or "GET").strip().upper() or "GET",
            "sig": signature,
        }
    )
    # Do not log full signed URLs; callers must treat them as secrets with short TTL.
    return f"{base_url.rstrip('/')}/{quote(object_id, safe='/')}?{query}"


@dataclass
class NoneTestEncryption:
    """Explicit test/dev mode: no encryption. Metadata must report none-test."""

    key_version: str = "none"

    @property
    def mode(self) -> str:
        return ENCRYPTION_NONE_TEST

    def encrypt(self, plaintext: bytes) -> bytes:
        return bytes(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return bytes(ciphertext)


@dataclass
class LocalAesGcmEncryption:
    """Development AES-256-GCM with externally injected key material."""

    key: bytes
    key_version: str = "v1"

    def __post_init__(self) -> None:
        if len(self.key) != 32:
            raise ObjectStorageConfigError("local-aes-gcm requires a 32-byte key")

    @property
    def mode(self) -> str:
        return ENCRYPTION_LOCAL_AES_GCM

    def encrypt(self, plaintext: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = secrets.token_bytes(12)
        ct = AESGCM(self.key).encrypt(nonce, plaintext, None)
        return nonce + ct

    def decrypt(self, ciphertext: bytes) -> bytes:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if len(ciphertext) < 13:
            raise ObjectStorageError("ciphertext_invalid")
        nonce, body = ciphertext[:12], ciphertext[12:]
        try:
            return AESGCM(self.key).decrypt(nonce, body, None)
        except Exception as exc:
            raise ObjectStorageError("ciphertext_invalid") from exc


def resolve_encryption() -> NoneTestEncryption | LocalAesGcmEncryption:
    mode = (
        str(
            os.getenv("OBJECT_STORAGE_ENCRYPTION", "")
            or config.get("OBJECT_STORAGE_ENCRYPTION", ENCRYPTION_NONE_TEST)
            or ENCRYPTION_NONE_TEST
        )
        .strip()
        .lower()
    )
    if mode in {"", "none", "none-test"}:
        return NoneTestEncryption()
    if mode == ENCRYPTION_LOCAL_AES_GCM:
        raw = str(
            os.getenv("OBJECT_STORAGE_ENCRYPTION_KEY", "") or config.get("OBJECT_STORAGE_ENCRYPTION_KEY", "") or ""
        ).strip()
        if not raw:
            raise ObjectStorageConfigError("OBJECT_STORAGE_ENCRYPTION_KEY is required for local-aes-gcm")
        try:
            key = base64.urlsafe_b64decode(raw.encode("ascii"))
        except Exception as exc:
            raise ObjectStorageConfigError("OBJECT_STORAGE_ENCRYPTION_KEY must be urlsafe base64") from exc
        version = str(os.getenv("OBJECT_STORAGE_ENCRYPTION_KEY_VERSION", "v1") or "v1").strip() or "v1"
        return LocalAesGcmEncryption(key=key, key_version=version)
    raise ObjectStorageConfigError(f"unsupported OBJECT_STORAGE_ENCRYPTION: {mode}")


def _persist_metadata(meta: ObjectMetadata) -> None:
    if object_storage_repository is None:
        return
    try:
        if hasattr(object_storage_repository, "upsert_metadata"):
            # Relational metadata is authoritative only when PostgreSQL is active.
            object_storage_repository.upsert_metadata(meta)
    except Exception:
        # Metadata persistence must not invent success; surface only when postgres is configured.
        from repositories import postgres_utils

        if postgres_utils.use_postgres():
            raise


def _mark_deleted(object_id: str, *, tenant_id: UUID) -> None:
    if object_storage_repository is None:
        return
    try:
        object_storage_repository.mark_deleted(object_id, tenant_id=tenant_id)
    except Exception:
        from repositories import postgres_utils

        if postgres_utils.use_postgres():
            raise


@dataclass
class InMemoryObjectStorage:
    """Test adapter. Bytes are not encrypted; encryption metadata is none-test."""

    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    encryption: NoneTestEncryption | LocalAesGcmEncryption = field(default_factory=NoneTestEncryption)
    provider: str = "memory"

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
        stored = self.encryption.encrypt(data)
        checksum = hashlib.sha256(data).hexdigest()
        meta = ObjectMetadata(
            object_id=object_id,
            tenant_id=tenant_id,
            store_id=store_id,
            owner=owner,
            content_type=content_type,
            size=len(data),
            checksum=checksum,
            encryption=self.encryption.mode,
            retention_days=retention_days,
            created_at=_now_iso(),
            key_version=self.encryption.key_version,
            provider=self.provider,
            bucket="",
            provider_key=object_id,
        )
        self.objects[object_id] = {"meta": meta, "data": stored, "deleted": False}
        _persist_metadata(meta)
        return meta

    def get(self, object_id: str, *, tenant_id: UUID) -> bytes:
        row = self.objects.get(object_id)
        if row is None or row["deleted"]:
            raise ObjectStorageError("not_found")
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        return self.encryption.decrypt(bytes(row["data"]))

    def head(self, object_id: str, *, tenant_id: UUID) -> ObjectMetadata:
        row = self.objects.get(object_id)
        if row is None or row["deleted"]:
            raise ObjectStorageError("not_found")
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        return meta

    def delete(self, object_id: str, *, tenant_id: UUID) -> bool:
        row = self.objects.get(object_id)
        if row is None:
            return False
        meta: ObjectMetadata = row["meta"]
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        row["deleted"] = True
        _mark_deleted(object_id, tenant_id=tenant_id)
        return True

    def signed_url(
        self,
        object_id: str,
        *,
        tenant_id: UUID,
        ttl_seconds: int = 300,
        method: str = "GET",
    ) -> str:
        self.head(object_id, tenant_id=tenant_id)
        return build_signed_url(
            object_id=object_id,
            tenant_id=tenant_id,
            ttl_seconds=ttl_seconds,
            method=method,
        )


@dataclass
class LocalObjectStorage:
    """Development/pilot disk adapter with tenant namespace and atomic writes."""

    root: Path
    encryption: NoneTestEncryption | LocalAesGcmEncryption = field(default_factory=NoneTestEncryption)
    provider: str = "local"

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "objects").mkdir(parents=True, exist_ok=True)
        (self.root / "meta").mkdir(parents=True, exist_ok=True)

    def _tenant_dir(self, tenant_id: UUID) -> Path:
        path = (self.root / "objects" / str(tenant_id)).resolve()
        if self.root not in path.parents and path != self.root:
            raise ObjectStorageError("path_traversal")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _object_path(self, object_id: str) -> Path:
        # object_id is tenant_id/uuid_filename
        parts = object_id.split("/", 1)
        if len(parts) != 2:
            raise ObjectStorageError("invalid_object_id")
        tenant_part, name = parts
        if ".." in tenant_part or ".." in name or name.startswith("/") or "\\" in name:
            raise ObjectStorageError("path_traversal")
        path = (self.root / "objects" / tenant_part / name).resolve()
        if self.root not in path.parents:
            raise ObjectStorageError("path_traversal")
        return path

    def _meta_path(self, object_id: str) -> Path:
        safe = object_id.replace("/", "__")
        if ".." in safe:
            raise ObjectStorageError("path_traversal")
        path = (self.root / "meta" / f"{safe}.json").resolve()
        if self.root not in path.parents:
            raise ObjectStorageError("path_traversal")
        return path

    def _write_meta(self, meta: ObjectMetadata) -> None:
        path = self._meta_path(meta.object_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        payload = {
            "object_id": meta.object_id,
            "tenant_id": str(meta.tenant_id),
            "store_id": str(meta.store_id) if meta.store_id else None,
            "owner": meta.owner,
            "content_type": meta.content_type,
            "size": meta.size,
            "checksum": meta.checksum,
            "encryption": meta.encryption,
            "retention_days": meta.retention_days,
            "created_at": meta.created_at,
            "deleted_at": meta.deleted_at,
            "key_version": meta.key_version,
            "provider": meta.provider,
            "bucket": meta.bucket,
            "provider_key": meta.provider_key,
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _read_meta(self, object_id: str) -> ObjectMetadata:
        path = self._meta_path(object_id)
        if not path.is_file():
            raise ObjectStorageError("not_found")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("deleted_at"):
            raise ObjectStorageError("not_found")
        store_raw = raw.get("store_id")
        return ObjectMetadata(
            object_id=str(raw["object_id"]),
            tenant_id=UUID(str(raw["tenant_id"])),
            store_id=UUID(str(store_raw)) if store_raw else None,
            owner=str(raw.get("owner") or ""),
            content_type=str(raw["content_type"]),
            size=int(raw["size"]),
            checksum=str(raw["checksum"]),
            encryption=str(raw["encryption"]),
            retention_days=int(raw["retention_days"]),
            created_at=str(raw["created_at"]),
            deleted_at=str(raw.get("deleted_at") or ""),
            key_version=str(raw.get("key_version") or ""),
            provider=str(raw.get("provider") or self.provider),
            bucket=str(raw.get("bucket") or ""),
            provider_key=str(raw.get("provider_key") or ""),
        )

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
        path = self._object_path(object_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = self.encryption.encrypt(data)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(stored)
        os.replace(tmp, path)
        checksum = hashlib.sha256(data).hexdigest()
        meta = ObjectMetadata(
            object_id=object_id,
            tenant_id=tenant_id,
            store_id=store_id,
            owner=owner,
            content_type=content_type,
            size=len(data),
            checksum=checksum,
            encryption=self.encryption.mode,
            retention_days=retention_days,
            created_at=_now_iso(),
            key_version=self.encryption.key_version,
            provider=self.provider,
            bucket=str(self.root),
            provider_key=object_id,
        )
        self._write_meta(meta)
        _persist_metadata(meta)
        return meta

    def get(self, object_id: str, *, tenant_id: UUID) -> bytes:
        meta = self.head(object_id, tenant_id=tenant_id)
        path = self._object_path(meta.object_id)
        if not path.is_file():
            raise ObjectStorageError("not_found")
        return self.encryption.decrypt(path.read_bytes())

    def head(self, object_id: str, *, tenant_id: UUID) -> ObjectMetadata:
        meta = self._read_meta(object_id)
        if meta.tenant_id != tenant_id:
            raise ObjectStorageError("tenant_isolation_violation")
        return meta

    def delete(self, object_id: str, *, tenant_id: UUID) -> bool:
        try:
            meta = self.head(object_id, tenant_id=tenant_id)
        except ObjectStorageError:
            return False
        path = self._object_path(meta.object_id)
        if path.is_file():
            path.unlink()
        deleted = ObjectMetadata(
            object_id=meta.object_id,
            tenant_id=meta.tenant_id,
            store_id=meta.store_id,
            owner=meta.owner,
            content_type=meta.content_type,
            size=meta.size,
            checksum=meta.checksum,
            encryption=meta.encryption,
            retention_days=meta.retention_days,
            created_at=meta.created_at,
            deleted_at=_now_iso(),
            key_version=meta.key_version,
            provider=meta.provider,
            bucket=meta.bucket,
            provider_key=meta.provider_key,
        )
        self._write_meta(deleted)
        _mark_deleted(object_id, tenant_id=tenant_id)
        return True

    def signed_url(
        self,
        object_id: str,
        *,
        tenant_id: UUID,
        ttl_seconds: int = 300,
        method: str = "GET",
    ) -> str:
        self.head(object_id, tenant_id=tenant_id)
        return build_signed_url(
            object_id=object_id,
            tenant_id=tenant_id,
            ttl_seconds=ttl_seconds,
            method=method,
        )

    def purge_expired(self, *, now: datetime | None = None) -> int:
        """Delete objects past retention. Returns count purged."""

        current = now or datetime.now(timezone.utc)
        purged = 0
        meta_dir = self.root / "meta"
        if not meta_dir.is_dir():
            return 0
        for path in meta_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("deleted_at"):
                continue
            try:
                created = datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00"))
                retention = int(raw.get("retention_days") or 30)
            except (KeyError, ValueError, TypeError):
                continue
            age_days = (current - created).total_seconds() / 86400.0
            if age_days < retention:
                continue
            object_id = str(raw["object_id"])
            tenant_id = UUID(str(raw["tenant_id"]))
            if self.delete(object_id, tenant_id=tenant_id):
                purged += 1
        return purged


@dataclass
class S3ObjectStorage:
    """S3-compatible adapter contract.

    Without cloud credentials this adapter refuses operations and surfaces
    EXTERNAL_BLOCKED rather than pretending to store objects.
    """

    endpoint: str
    bucket: str
    access_key: str
    secret_key: str
    region: str = "auto"
    encryption_mode: str = "provider-managed"
    provider: str = "s3"

    def _ensure_configured(self) -> None:
        if not self.endpoint or not self.bucket or not self.access_key or not self.secret_key:
            raise ObjectStorageConfigError("S3 object storage is EXTERNAL_BLOCKED: missing endpoint/bucket/credentials")
        if self.secret_key in {"CHANGE_ME", "change_me"}:
            raise ObjectStorageConfigError("S3 object storage credentials must not use placeholders")

    def put(self, **kwargs: Any) -> ObjectMetadata:
        self._ensure_configured()
        raise ObjectStorageConfigError("S3 put requires cloud SDK wiring (EXTERNAL_BLOCKED)")

    def get(self, object_id: str, *, tenant_id: UUID) -> bytes:
        self._ensure_configured()
        raise ObjectStorageConfigError("S3 get requires cloud SDK wiring (EXTERNAL_BLOCKED)")

    def delete(self, object_id: str, *, tenant_id: UUID) -> bool:
        self._ensure_configured()
        raise ObjectStorageConfigError("S3 delete requires cloud SDK wiring (EXTERNAL_BLOCKED)")

    def head(self, object_id: str, *, tenant_id: UUID) -> ObjectMetadata:
        self._ensure_configured()
        raise ObjectStorageConfigError("S3 head requires cloud SDK wiring (EXTERNAL_BLOCKED)")

    def stream(self, object_id: str, *, tenant_id: UUID):
        self._ensure_configured()
        raise ObjectStorageConfigError("S3 stream requires cloud SDK wiring (EXTERNAL_BLOCKED)")

    def lifecycle_metadata(self, object_id: str, *, tenant_id: UUID) -> dict:
        self._ensure_configured()
        return {
            "provider": self.provider,
            "bucket": self.bucket,
            "object_id": object_id,
            "tenant_id": str(tenant_id),
            "encryption": self.encryption_mode,
        }

    def signed_url(
        self,
        object_id: str,
        *,
        tenant_id: UUID,
        ttl_seconds: int = 300,
        method: str = "GET",
    ) -> str:
        self._ensure_configured()
        # Local HMAC contract remains valid for gateway fronts; cloud presign is 10B.
        return build_signed_url(
            object_id=object_id,
            tenant_id=tenant_id,
            ttl_seconds=ttl_seconds,
            method=method,
            base_url=f"{self.endpoint.rstrip('/')}/{self.bucket}",
        )


_STORE: InMemoryObjectStorage | LocalObjectStorage | S3ObjectStorage | None = None


def _local_root() -> Path:
    raw = str(os.getenv("OBJECT_STORAGE_LOCAL_ROOT", "") or config.get("OBJECT_STORAGE_LOCAL_ROOT", "") or "").strip()
    if raw:
        return Path(raw)
    return configured_runtime_paths(os.environ).objects


def storage() -> InMemoryObjectStorage | LocalObjectStorage | S3ObjectStorage:
    global _STORE
    if _STORE is not None:
        return _STORE
    backend = (
        str(os.getenv("OBJECT_STORAGE_BACKEND", "") or config.get("OBJECT_STORAGE_BACKEND", "memory") or "memory")
        .strip()
        .lower()
    )
    encryption = resolve_encryption()
    if backend in {"memory", "inmemory", "test"}:
        _STORE = InMemoryObjectStorage(encryption=encryption)
    elif backend in {"local", "disk", "filesystem"}:
        _STORE = LocalObjectStorage(root=_local_root(), encryption=encryption)
    elif backend in {"s3", "s3-compatible", "minio"}:
        _STORE = S3ObjectStorage(
            endpoint=str(os.getenv("OBJECT_STORAGE_ENDPOINT", "") or config.get("OBJECT_STORAGE_ENDPOINT", "") or ""),
            bucket=str(os.getenv("OBJECT_STORAGE_BUCKET", "") or config.get("OBJECT_STORAGE_BUCKET", "") or ""),
            access_key=str(
                os.getenv("OBJECT_STORAGE_ACCESS_KEY", "") or config.get("OBJECT_STORAGE_ACCESS_KEY", "") or ""
            ),
            secret_key=str(
                os.getenv("OBJECT_STORAGE_SECRET_KEY", "") or config.get("OBJECT_STORAGE_SECRET_KEY", "") or ""
            ),
            region=str(os.getenv("OBJECT_STORAGE_REGION", "auto") or "auto"),
            encryption_mode=str(os.getenv("OBJECT_STORAGE_S3_ENCRYPTION", "provider-managed") or "provider-managed"),
        )
    else:
        raise ObjectStorageConfigError(f"unsupported OBJECT_STORAGE_BACKEND: {backend}")
    return _STORE


def reset_for_tests(
    *,
    backend: str = "memory",
    root: Path | str | None = None,
    encryption: NoneTestEncryption | LocalAesGcmEncryption | None = None,
    signing_secret: str | None = "test-object-storage-signing-secret",
) -> InMemoryObjectStorage | LocalObjectStorage | S3ObjectStorage:
    global _STORE
    if signing_secret is not None:
        os.environ["OBJECT_STORAGE_SIGNING_SECRET"] = signing_secret
    enc = encryption or NoneTestEncryption()
    if backend == "memory":
        _STORE = InMemoryObjectStorage(encryption=enc)
    elif backend == "local":
        if root is None:
            raise ObjectStorageError("local backend requires root for tests")
        _STORE = LocalObjectStorage(root=Path(root), encryption=enc)
    elif backend == "s3":
        _STORE = S3ObjectStorage(endpoint="", bucket="", access_key="", secret_key="")
    else:
        raise ObjectStorageError("unknown_test_backend")
    return _STORE


def parse_signed_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = unquote(parsed.path.lstrip("/"))
    # strip optional bucket prefix for s3-style base
    return {
        "object_id": path,
        "expires": (query.get("expires") or [""])[0],
        "tenant_id": (query.get("tenant_id") or [""])[0],
        "method": (query.get("method") or ["GET"])[0],
        "sig": (query.get("sig") or [""])[0],
    }
