"""Security contracts for trusted local-pilot provisioning output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.scripts import bootstrap_local_pilot


def test_device_credential_bundle_must_be_outside_repository() -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        bootstrap_local_pilot._external_secret_path(
            bootstrap_local_pilot.REPOSITORY_ROOT / "local-device-secret.json"
        )


def test_device_credential_bundle_is_private_and_never_overwritten(tmp_path: Path) -> None:
    bundle = tmp_path / "secrets" / "kiosk-1.json"
    payload = {"key_id": "dev_key", "credential": "raw-secret-value"}

    bootstrap_local_pilot._write_secret_bundle(bundle, payload)

    assert bundle.stat().st_mode & 0o777 == 0o600
    assert bundle.parent.stat().st_mode & 0o777 == 0o700
    assert json.loads(bundle.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        bootstrap_local_pilot._write_secret_bundle(bundle, {"credential": "replacement"})
    assert json.loads(bundle.read_text(encoding="utf-8")) == payload


def test_generated_admin_password_is_strong_private_and_idempotent(tmp_path: Path) -> None:
    bundle = tmp_path / "secrets" / "admin.json"

    first = bootstrap_local_pilot._generated_admin_password(bundle, "admin")
    second = bootstrap_local_pilot._generated_admin_password(bundle, "admin")

    assert first == second
    assert len(first) >= 32
    assert bundle.stat().st_mode & 0o777 == 0o600
    assert json.loads(bundle.read_text(encoding="utf-8")) == {
        "version": 1,
        "login_identity": "admin",
        "password": first,
    }


def test_generated_pilot_environment_is_private_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = tmp_path / "database_url"
    migration_url = tmp_path / "migration_database_url"
    database_url.write_text("postgresql://runtime", encoding="utf-8")
    migration_url.write_text("postgresql://migration", encoding="utf-8")
    database_url.chmod(0o600)
    migration_url.chmod(0o600)
    monkeypatch.setenv("DATABASE_URL_FILE", str(database_url))
    monkeypatch.setenv("MIGRATION_DATABASE_URL_FILE", str(migration_url))
    output = tmp_path / "private" / "local-pilot.env"

    bootstrap_local_pilot._write_pilot_environment(
        output_path=output,
        tenant_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000001"),
        store_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000002"),
        device_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000003"),
        admin_login="admin",
    )

    text = output.read_text(encoding="utf-8")
    assert output.stat().st_mode & 0o777 == 0o600
    assert "APP_ENV=pilot" in text
    assert "ENABLE_LEGACY_KIOSK_TOKEN=false" in text
    assert "ADMIN_LOCAL_MANAGER_AUTH_ENABLED=false" in text
    assert "ENABLE_NGROK=false" in text
    assert "DEFAULT_DEVICE_ID=00000000-0000-4000-8000-000000000003" in text
    assert "ADMIN_MEMBER_REF_SECRET=" in text
    assert "OBJECT_STORAGE_SIGNING_SECRET=" in text
    assert "postgresql://runtime" not in text

    output.write_text(text.replace("ENABLE_NGROK=false", "ENABLE_NGROK=true"), encoding="utf-8")
    output.chmod(0o600)
    bootstrap_local_pilot._write_pilot_environment(
        output_path=output,
        tenant_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000001"),
        store_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000002"),
        device_id=bootstrap_local_pilot.UUID("00000000-0000-4000-8000-000000000003"),
        admin_login="admin",
    )
    assert "ENABLE_NGROK=false" in output.read_text(encoding="utf-8")
