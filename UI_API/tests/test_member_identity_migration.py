"""Milestone 1F Member UUID and protected phone contracts."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_migration_moves_member_identity_to_uuid_and_dual_references() -> None:
    sql = (
        ROOT / "UI_API/backend/schemas/migrations/0006_member_uuid_pii_migration.sql"
    ).read_text(encoding="utf-8")
    for fragment in (
        "ALTER TABLE members ADD COLUMN id UUID",
        "phone_lookup_hash TEXT",
        "phone_encrypted TEXT",
        "phone_masked TEXT",
        "key_version TEXT",
        "ADD COLUMN member_id UUID",
        "PRIMARY KEY (id)",
        "UNIQUE (tenant_id, phone_lookup_hash)",
    ):
        assert fragment in sql
    for table in ("member_preferences", "member_sessions", "member_orders"):
        assert f"ALTER TABLE {table}" in sql
    assert "CREATE EXTENSION" not in sql.upper()


def test_phone_protection_is_tenant_scoped_versioned_and_reversible() -> None:
    from services.member_key_provider import DevelopmentMemberKeyProvider
    from services.member_pii_service import protect_phone, reveal_phone

    provider = DevelopmentMemberKeyProvider(active_version="v2")
    tenant_a = uuid4()
    tenant_b = uuid4()
    protected_a = protect_phone("0912345678", tenant_a, provider)
    protected_b = protect_phone("0912345678", tenant_b, provider)

    assert protected_a.key_version == "v2"
    assert protected_a.phone_masked == "0912-***-678"
    assert "0912345678" not in protected_a.phone_encrypted
    assert protected_a.phone_lookup_hash != protected_b.phone_lookup_hash
    assert reveal_phone(protected_a.phone_encrypted, protected_a.key_version, provider) == "0912345678"


def test_lookup_hash_changes_with_managed_key_version() -> None:
    from services.member_key_provider import DevelopmentMemberKeyProvider
    from services.member_pii_service import phone_lookup_hash

    tenant_id = uuid4()
    v1 = DevelopmentMemberKeyProvider(active_version="v1")
    v2 = DevelopmentMemberKeyProvider(active_version="v2")
    assert phone_lookup_hash("0912345678", tenant_id, v1) != phone_lookup_hash(
        "0912345678", tenant_id, v2
    )


def test_environment_provider_fails_safely_without_key_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.member_key_provider import EnvironmentMemberKeyProvider, MemberKeyConfigurationError

    for name in (
        "MEMBER_PHONE_KEY_VERSION",
        "MEMBER_PHONE_LOOKUP_PEPPER",
        "MEMBER_PHONE_ENCRYPTION_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(MemberKeyConfigurationError) as exc:
        EnvironmentMemberKeyProvider()
    message = str(exc.value)
    assert "MEMBER_PHONE_LOOKUP_PEPPER" not in message
    assert "MEMBER_PHONE_ENCRYPTION_KEY" not in message


def test_member_identity_feature_flags_and_crypto_dependency_are_declared() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    config_source = (ROOT / "UI_API/config.py").read_text(encoding="utf-8")
    requirements = (ROOT / "UI_API/requirements-ci.txt").read_text(encoding="utf-8")
    for name in ("MEMBER_IDENTITY_READ_MODE", "MEMBER_IDENTITY_DUAL_WRITE"):
        assert name in env_example
        assert name in config_source
    assert "cryptography==" in requirements


def test_repository_and_verifier_expose_uuid_contract_without_pii_output() -> None:
    repository = (ROOT / "UI_API/backend/repositories/member_repository.py").read_text(
        encoding="utf-8"
    )
    verifier = (
        ROOT / "UI_API/backend/scripts/verify_member_identity_migration.py"
    ).read_text(encoding="utf-8")
    assert "def get_member_by_id_scoped(" in repository
    assert "def get_member_by_phone_scoped(" in repository
    for violation in (
        "missing_member_id",
        "duplicate_lookup_hash",
        "reference_mismatch",
        "orphan_member_reference",
        "dual_write_drift",
    ):
        assert violation in verifier
    assert '"phone"' not in verifier
    assert "phone_encrypted" not in verifier
