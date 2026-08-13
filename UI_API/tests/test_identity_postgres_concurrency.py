"""PostgreSQL concurrency evidence for device credential rotation."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from capabilities.identity_access import device_identity_service
from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="identity concurrency evidence requires PostgreSQL",
    )
)

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")
SCOPE = CommercialScope(TENANT, STORE, DEVICE)


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


def _purge(*credential_ids: uuid.UUID) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        related: set[str] = set()
        for credential_id in credential_ids:
            cur.execute(
                "SELECT id FROM device_credentials WHERE id = %s OR rotated_from_credential_id = %s",
                (str(credential_id), str(credential_id)),
            )
            related.update(str(row["id"]) for row in cur.fetchall())
        for credential_id in related:
            cur.execute("DELETE FROM device_sessions WHERE credential_id = %s", (credential_id,))
            cur.execute("DELETE FROM device_credential_events WHERE credential_id = %s", (credential_id,))
            cur.execute(
                "UPDATE device_credentials SET rotated_from_credential_id = NULL WHERE id = %s",
                (credential_id,),
            )
        for credential_id in related:
            cur.execute("DELETE FROM device_credentials WHERE id = %s", (credential_id,))
        conn.commit()


def test_concurrent_rotation_has_one_winner_and_one_replacement():
    original = device_identity_service.issue_device_credential(_manager(), SCOPE, DEVICE)

    def rotate():
        try:
            return device_identity_service.rotate_device_credential(_manager(), SCOPE, original.credential_id)
        except Exception as exc:  # preserve the losing transaction for assertions
            return exc

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: rotate(), (None, None)))

        winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
        losers = [outcome for outcome in outcomes if isinstance(outcome, ValueError)]
        assert len(winners) == 1, outcomes
        assert len(losers) == 1, outcomes

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS replacements FROM device_credentials WHERE rotated_from_credential_id = %s",
                (str(original.credential_id),),
            )
            assert int(cur.fetchone()["replacements"]) == 1
            cur.execute(
                "SELECT count(*) AS rotations FROM device_credential_events "
                "WHERE credential_id = %s AND event_type = 'device_credential_rotated'",
                (str(winners[0].credential_id),),
            )
            assert int(cur.fetchone()["rotations"]) == 1
    finally:
        _purge(original.credential_id)
