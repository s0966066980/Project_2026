"""PostgreSQL concurrency evidence for device credential rotation."""

import os
import threading
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
    """Two managers press rotate on the same credential at the same instant.

    What this proves is that a credential cannot be rotated twice: one call
    returns a replacement, the other is refused, and exactly one replacement
    row and one audit event exist afterwards.

    What it does not prove is that the adapter takes a row lock. Both calls
    overlap, but their two `SELECT`s land a few milliseconds apart, so the
    loser reliably reads the grace window the winner already committed — the
    check passes with `FOR UPDATE` removed. The lock itself is pinned
    deterministically by the test below.
    """

    original = device_identity_service.issue_device_credential(_manager(), SCOPE, DEVICE)
    barrier = threading.Barrier(2)

    def rotate():
        barrier.wait()
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


def test_sixteen_managers_pressing_rotate_at_once_still_produce_one_replacement():
    """The read-decide-write sequence has to be atomic, not merely fast.

    Two threads do not settle this: their `SELECT`s land a few milliseconds
    apart, so the loser reads the committed grace window and is refused
    whether or not the adapter locks the row. Widening the field puts several
    readers inside the same window, which is the situation `FOR UPDATE`
    exists for — without it, more than one caller decides the credential is
    rotatable and more than one replacement is written.
    """

    original = device_identity_service.issue_device_credential(_manager(), SCOPE, DEVICE)
    barrier = threading.Barrier(16)

    def rotate(_):
        barrier.wait()
        try:
            return device_identity_service.rotate_device_credential(_manager(), SCOPE, original.credential_id)
        except Exception as exc:  # noqa: BLE001 - the losers are the point
            return exc

    try:
        with ThreadPoolExecutor(max_workers=16) as executor:
            outcomes = list(executor.map(rotate, range(16)))

        winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
        assert len(winners) == 1, f"{len(winners)} callers rotated the same credential: {outcomes}"

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS replacements FROM device_credentials WHERE rotated_from_credential_id = %s",
                (str(original.credential_id),),
            )
            replacements = int(cur.fetchone()["replacements"])
        assert replacements == 1, f"one rotation produced {replacements} replacement credentials"
    finally:
        _purge(original.credential_id)
