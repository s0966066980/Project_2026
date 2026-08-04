"""Tenant-scoped keyed lookup and authenticated phone encryption."""

import hashlib
import hmac
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

import config
from models.member_identity import ProtectedPhone
from services.member_key_provider import (
    DevelopmentMemberKeyProvider,
    EnvironmentMemberKeyProvider,
    MemberKeyConfigurationError,
    MemberKeyProvider,
)


class MemberPiiProtectionError(RuntimeError):
    pass


def configured_key_provider() -> MemberKeyProvider:
    if str(config.APP_ENV).lower() in {"production", "staging"}:
        return EnvironmentMemberKeyProvider()
    version = str(config.get("MEMBER_PHONE_KEY_VERSION", "v1") or "v1")
    return DevelopmentMemberKeyProvider(version if version in {"v1", "v2"} else "v1")


def normalize_phone(phone: str) -> str:
    normalized = "".join(character for character in str(phone or "") if character.isdigit())
    if len(normalized) != 10:
        raise ValueError("A normalized ten-digit phone is required")
    return normalized


def mask_phone(phone: str) -> str:
    normalized = normalize_phone(phone)
    return f"{normalized[:4]}-***-{normalized[7:]}"


def phone_lookup_hash(phone: str, tenant_id: UUID, provider: MemberKeyProvider) -> str:
    material = provider.material()
    message = f"{tenant_id}:{normalize_phone(phone)}".encode()
    digest = hmac.new(material.lookup_pepper, message, hashlib.sha256).hexdigest()
    return f"{material.version}:{digest}"


def protect_phone(phone: str, tenant_id: UUID, provider: MemberKeyProvider) -> ProtectedPhone:
    normalized = normalize_phone(phone)
    material = provider.material()
    encrypted = Fernet(material.encryption_key).encrypt(normalized.encode()).decode()
    return ProtectedPhone(
        phone_lookup_hash=phone_lookup_hash(normalized, tenant_id, provider),
        phone_encrypted=encrypted,
        phone_masked=mask_phone(normalized),
        key_version=material.version,
    )


def reveal_phone(ciphertext: str, key_version: str, provider: MemberKeyProvider) -> str:
    try:
        material = provider.material(key_version)
        return normalize_phone(Fernet(material.encryption_key).decrypt(ciphertext.encode()).decode())
    except (InvalidToken, UnicodeDecodeError, ValueError, MemberKeyConfigurationError) as exc:
        raise MemberPiiProtectionError("Member phone could not be decrypted") from exc
