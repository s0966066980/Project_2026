"""Milestone 5B: truthful object storage metadata, HMAC signed access, local adapter."""

from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")
STORE = UUID("00000000-0000-4000-8000-000000000002")
OTHER = UUID("00000000-0000-4000-8000-000000000099")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OBJECT_STORAGE_SIGNING_SECRET", "test-object-storage-signing-secret")
    monkeypatch.setenv("OBJECT_STORAGE_ENCRYPTION", "none-test")
    monkeypatch.delenv("OBJECT_STORAGE_ENCRYPTION_KEY", raising=False)
    yield


def test_inmemory_metadata_is_none_test_not_false_encryption() -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="memory")
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"hello",
        filename="note.txt",
    )
    assert meta.encryption == "none-test"
    assert meta.encryption != "aes-256-gcm-envelope"
    assert meta.provider == "memory"
    assert meta.checksum
    assert store.get(meta.object_id, tenant_id=TENANT) == b"hello"


def test_local_disk_adapter_atomic_tenant_isolation_and_traversal(tmp_path: Path) -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="local", root=tmp_path / "objs")
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="application/json",
        data=b'{"ok":true}',
        filename="../escape.json",
    )
    assert ".." not in meta.object_id
    assert meta.encryption == "none-test"
    assert meta.provider == "local"
    assert store.get(meta.object_id, tenant_id=TENANT) == b'{"ok":true}'
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=OTHER)
    assert store.delete(meta.object_id, tenant_id=TENANT) is True
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=TENANT)


def test_hmac_signed_url_valid_tamper_and_expiry() -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="memory")
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"payload",
        filename="a.txt",
    )
    url = store.signed_url(meta.object_id, tenant_id=TENANT, ttl_seconds=60, method="GET")
    parsed = object_storage_service.parse_signed_url(url)
    assert parsed["tenant_id"] == str(TENANT)
    assert "sig=" in url
    assert object_storage_service.verify_signed_access(
        object_id=meta.object_id,
        tenant_id=TENANT,
        expires=int(parsed["expires"]),
        signature=parsed["sig"],
        method="GET",
    )
    # Tamper signature
    assert not object_storage_service.verify_signed_access(
        object_id=meta.object_id,
        tenant_id=TENANT,
        expires=int(parsed["expires"]),
        signature=parsed["sig"][:-2] + "aa",
        method="GET",
    )
    # Method mismatch
    assert not object_storage_service.verify_signed_access(
        object_id=meta.object_id,
        tenant_id=TENANT,
        expires=int(parsed["expires"]),
        signature=parsed["sig"],
        method="PUT",
    )
    # Expiry
    past = int(time.time()) - 10
    expired_sig = object_storage_service.sign_access(
        object_id=meta.object_id,
        tenant_id=TENANT,
        expires=past,
        method="GET",
    )
    assert not object_storage_service.verify_signed_access(
        object_id=meta.object_id,
        tenant_id=TENANT,
        expires=past,
        signature=expired_sig,
        method="GET",
    )


def test_production_missing_signing_secret_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import object_storage_service

    monkeypatch.delenv("OBJECT_STORAGE_SIGNING_SECRET", raising=False)
    monkeypatch.setattr(object_storage_service.config, "APP_ENV", "production")
    monkeypatch.setattr(object_storage_service.config, "is_commercial_runtime", lambda: True)
    monkeypatch.setattr(object_storage_service.config, "is_security_enforced", lambda: True)
    with pytest.raises(object_storage_service.ObjectStorageConfigError):
        object_storage_service._signing_secret(require=True)


def test_local_aes_gcm_encryption_roundtrip_and_truthful_metadata(tmp_path: Path) -> None:
    from services import object_storage_service

    key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    enc = object_storage_service.LocalAesGcmEncryption(
        key=base64.urlsafe_b64decode(key.encode("ascii")),
        key_version="test-v1",
    )
    store = object_storage_service.reset_for_tests(
        backend="local",
        root=tmp_path / "enc",
        encryption=enc,
    )
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"secret-bytes",
        filename="secure.txt",
    )
    assert meta.encryption == "local-aes-gcm"
    assert meta.key_version == "test-v1"
    raw_path = (tmp_path / "enc" / "objects" / str(TENANT)).glob("*_secure.txt")
    on_disk = next(raw_path).read_bytes()
    assert on_disk != b"secret-bytes"
    assert store.get(meta.object_id, tenant_id=TENANT) == b"secret-bytes"


def test_s3_contract_without_credentials_is_external_blocked() -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="s3")
    with pytest.raises(object_storage_service.ObjectStorageConfigError) as exc:
        store.put(
            tenant_id=TENANT,
            store_id=STORE,
            owner="admin",
            content_type="text/plain",
            data=b"x",
            filename="a.txt",
        )
    assert "EXTERNAL_BLOCKED" in str(exc.value)


def test_content_type_and_size_limits() -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="memory")
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.put(
            tenant_id=TENANT,
            store_id=STORE,
            owner="admin",
            content_type="application/x-msdownload",
            data=b"bad",
            filename="x.bin",
        )
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.put(
            tenant_id=TENANT,
            store_id=STORE,
            owner="admin",
            content_type="text/plain",
            data=b"x" * (20 * 1024 * 1024 + 1),
            filename="big.txt",
        )


def test_retention_purge(tmp_path: Path) -> None:
    from services import object_storage_service

    store = object_storage_service.reset_for_tests(backend="local", root=tmp_path / "ret")
    assert isinstance(store, object_storage_service.LocalObjectStorage)
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"old",
        filename="old.txt",
        retention_days=1,
    )
    # Backdate metadata created_at
    meta_path = store._meta_path(meta.object_id)
    import json

    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    raw["created_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    meta_path.write_text(json.dumps(raw), encoding="utf-8")
    purged = store.purge_expired()
    assert purged == 1
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=TENANT)


def test_phase4_compatibility_signed_url_still_works() -> None:
    """Existing phase-4 isolation test contract remains valid with truthful metadata."""
    from services import object_storage_service

    object_storage_service.reset_for_tests()
    store = object_storage_service.storage()
    meta = store.put(
        tenant_id=TENANT,
        store_id=STORE,
        owner="admin",
        content_type="text/plain",
        data=b"hello",
        filename="../secret.txt",
    )
    assert ".." not in meta.object_id
    assert meta.encryption == "none-test"
    assert store.get(meta.object_id, tenant_id=TENANT) == b"hello"
    with pytest.raises(object_storage_service.ObjectStorageError):
        store.get(meta.object_id, tenant_id=OTHER)
    url = store.signed_url(meta.object_id, tenant_id=TENANT, ttl_seconds=60)
    assert "expires=" in url
    assert "sig=" in url
    assert store.delete(meta.object_id, tenant_id=TENANT) is True
