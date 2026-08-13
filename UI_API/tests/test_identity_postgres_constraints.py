"""PostgreSQL uniqueness and foreign-key evidence for device identity."""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from capabilities.identity_access import device_identity_service
from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from modules.identity._device_identity_service import hash_device_secret
from modules.identity.adapters import device_identity as device_identity_repository
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="device identity constraints require PostgreSQL",
    )
)

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")


def _manager() -> AdminPrincipal:
    return AdminPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=TENANT,
        allowed_store_ids=(STORE,),
        roles=("device-admin",),
        permissions=("*",),
        session_id=None,
        auth_method="device_admin",
    )


def _scope() -> CommercialScope:
    return CommercialScope(TENANT, STORE, DEVICE)


def _purge(credential_id: uuid.UUID) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM device_credential_events WHERE credential_id = %s", (str(credential_id),))
        cur.execute("DELETE FROM device_sessions WHERE credential_id = %s", (str(credential_id),))
        cur.execute("DELETE FROM device_credentials WHERE id = %s", (str(credential_id),))
        conn.commit()


def _direct_credential(*, device_id: uuid.UUID, key_id: str, credential_hash: str) -> dict:
    issued_at = datetime.now(timezone.utc)
    return device_identity_repository.create_device_credential(
        credential_id=uuid.uuid4(),
        tenant_id=TENANT,
        store_id=STORE,
        device_id=device_id,
        key_id=key_id,
        credential_hash=credential_hash,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(days=90),
    )


def test_duplicate_key_id_is_rejected_by_the_database():
    issued = device_identity_service.issue_device_credential(_manager(), _scope(), DEVICE)

    try:
        with pytest.raises(UniqueViolation):
            _direct_credential(
                device_id=DEVICE,
                key_id=issued.key_id,
                credential_hash=hash_device_secret("a-different-secret"),
            )
    finally:
        _purge(issued.credential_id)


def test_credential_for_an_unknown_device_is_rejected_by_the_foreign_key():
    with pytest.raises(ForeignKeyViolation):
        _direct_credential(
            device_id=uuid.uuid4(),
            key_id=f"dev_{uuid.uuid4().hex}",
            credential_hash=hash_device_secret("foreign-key-secret"),
        )
