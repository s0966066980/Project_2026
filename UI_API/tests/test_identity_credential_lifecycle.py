"""Device credential lifecycle against the database that actually stores it.

The Module Independence Gate for Identity asks for issue, rotate, revoke and
expiry; store isolation; wrong-device and wrong-store refusal; session replay
and expiry; and an audit trail that records what happened without recording the
secret. None of that is provable on SQLite: `authenticate_device_session`
returns `None` outright when PostgreSQL is not in use, so a SQLite run would
"pass" every negative case for the wrong reason.

These skip unless the run is really on PostgreSQL, and they clean up the rows
they create so the store they run against is left as they found it.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from capabilities.identity_access import device_identity_service
from models.admin_identity import AdminPrincipal
from models.commercial_scope import CommercialScope
from modules.identity.adapters import device_identity as device_identity_repository
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]

SEEDED_DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")
SEEDED_TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
SEEDED_STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _on_postgres() -> bool:
    return str(os.environ.get("DATABASE_BACKEND", "")).strip() == "postgresql" and postgres_utils.use_postgres()


pytestmark.append(pytest.mark.skipif(not _on_postgres(), reason="device identity is only stored in PostgreSQL"))


def _manager(store_ids=(SEEDED_STORE,)) -> AdminPrincipal:
    return AdminPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=SEEDED_TENANT,
        allowed_store_ids=tuple(store_ids),
        roles=("device-admin",),
        permissions=("*",),
        session_id=None,
        auth_method="device_admin",
    )


def _scope(store_id=SEEDED_STORE) -> CommercialScope:
    return CommercialScope(SEEDED_TENANT, store_id, SEEDED_DEVICE)


@pytest.fixture
def issued():
    """A credential for the seeded device, removed again afterwards."""

    credential = device_identity_service.issue_device_credential(_manager(), _scope(), SEEDED_DEVICE)
    yield credential
    _purge(credential.credential_id)


def _purge(*credential_ids: uuid.UUID) -> None:
    """Remove a credential and everything that points at it.

    Sessions and audit events carry foreign keys, and rotation leaves the
    replacement pointing back at what it replaced, so the order matters and a
    rotated pair has to go together.
    """

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for credential_id in credential_ids:
            cur.execute(
                "SELECT id FROM device_credentials WHERE id = %s OR rotated_from_credential_id = %s",
                (str(credential_id), str(credential_id)),
            )
            # The connection yields dict rows, matching the adapters.
            related = [str(row["id"]) for row in cur.fetchall()] or [str(credential_id)]
            for target in related:
                cur.execute("DELETE FROM device_sessions WHERE credential_id = %s", (target,))
                cur.execute("DELETE FROM device_credential_events WHERE credential_id = %s", (target,))
                cur.execute("UPDATE device_credentials SET rotated_from_credential_id = NULL WHERE id = %s", (target,))
            for target in related:
                cur.execute("DELETE FROM device_credentials WHERE id = %s", (target,))
        conn.commit()


def test_an_issued_credential_opens_a_session_and_names_its_device(issued):
    result = device_identity_service.create_device_session(issued.key_id, issued.credential)

    assert result.principal.device_id == SEEDED_DEVICE
    assert result.principal.store_id == SEEDED_STORE
    assert result.principal.auth_method == "device_session"
    assert result.token and result.token != issued.credential

    resolved = device_identity_service.authenticate_device_session(result.token)
    assert resolved is not None
    assert resolved.session_id == result.principal.session_id


def test_a_wrong_secret_for_a_real_key_is_refused(issued):
    from modules.identity._device_identity_service import DeviceAuthenticationError

    with pytest.raises(DeviceAuthenticationError):
        device_identity_service.create_device_session(issued.key_id, "not-the-credential")


def test_an_unknown_key_is_refused_without_saying_which_part_was_wrong(issued):
    from modules.identity._device_identity_service import DeviceAuthenticationError

    with pytest.raises(DeviceAuthenticationError) as unknown_key:
        device_identity_service.create_device_session(f"dev_{uuid.uuid4().hex}", issued.credential)
    with pytest.raises(DeviceAuthenticationError) as wrong_secret:
        device_identity_service.create_device_session(issued.key_id, "not-the-credential")

    assert str(unknown_key.value) == str(wrong_secret.value), (
        "the refusal distinguishes an unknown device from a wrong secret"
    )


def test_an_expired_credential_stops_opening_sessions(issued):
    from modules.identity._device_identity_service import DeviceAuthenticationError

    later = datetime.now(timezone.utc) + timedelta(days=3650)

    with pytest.raises(DeviceAuthenticationError):
        device_identity_service.create_device_session(issued.key_id, issued.credential, now=later)


def test_rotation_issues_a_new_secret_and_closes_the_old_one(issued):
    rotated = device_identity_service.rotate_device_credential(_manager(), _scope(), issued.credential_id)
    try:
        assert rotated.credential != issued.credential
        assert rotated.key_id != issued.key_id

        opened = device_identity_service.create_device_session(rotated.key_id, rotated.credential)
        assert opened.principal.device_id == SEEDED_DEVICE

        # The old credential keeps a grace window by design, then stops. Past
        # the window it must not open anything.
        from modules.identity._device_identity_service import DeviceAuthenticationError

        after_grace = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(DeviceAuthenticationError):
            device_identity_service.create_device_session(issued.key_id, issued.credential, now=after_grace)
    finally:
        _purge(rotated.credential_id)


def test_revocation_ends_the_credential_and_the_sessions_it_opened(issued):
    from modules.identity._device_identity_service import DeviceAuthenticationError

    session = device_identity_service.create_device_session(issued.key_id, issued.credential)
    assert device_identity_service.authenticate_device_session(session.token) is not None

    assert device_identity_service.revoke_device_credential(_manager(), _scope(), issued.credential_id) is True

    assert device_identity_service.authenticate_device_session(session.token) is None, (
        "a revoked credential left a live session behind"
    )
    with pytest.raises(DeviceAuthenticationError):
        device_identity_service.create_device_session(issued.key_id, issued.credential)


def test_revoking_twice_is_idempotent_and_audited_once(issued):
    """A repeated click is still "revoked"; the trail still says it happened once.

    Each call used to write another `device_credential_revoked` event, so one
    revocation read as three — a security record describing actions nobody
    took. The API answer stays True because the credential is revoked, which
    is what the caller asked for.
    """

    assert device_identity_service.revoke_device_credential(_manager(), _scope(), issued.credential_id) is True
    assert device_identity_service.revoke_device_credential(_manager(), _scope(), issued.credential_id) is True
    assert device_identity_service.revoke_device_credential(_manager(), _scope(), issued.credential_id) is True

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS events FROM device_credential_events "
            "WHERE credential_id = %s AND event_type = 'device_credential_revoked'",
            (str(issued.credential_id),),
        )
        recorded = int(cur.fetchone()["events"])

    assert recorded == 1, f"one revocation produced {recorded} audit events"


def test_a_manager_from_another_store_cannot_issue_for_this_device():
    other_store = uuid.uuid4()

    with pytest.raises(Exception) as refused:
        device_identity_service.issue_device_credential(
            _manager(store_ids=(other_store,)), _scope(store_id=other_store), SEEDED_DEVICE
        )

    assert refused.value is not None


def test_a_credential_cannot_be_revoked_from_another_store(issued):
    other_store = uuid.uuid4()

    revoked = device_identity_service.revoke_device_credential(
        _manager(store_ids=(other_store,)), _scope(store_id=other_store), issued.credential_id
    )

    assert revoked is False, "a credential was revoked from outside its store"
    assert device_identity_service.create_device_session(issued.key_id, issued.credential) is not None


def test_a_device_outside_the_scope_is_refused():
    with pytest.raises(ValueError):
        device_identity_service.issue_device_credential(_manager(), _scope(), uuid.uuid4())


def test_the_stored_credential_is_a_hash_and_not_the_secret(issued):
    row = device_identity_repository.find_device_credential(issued.key_id)

    assert row is not None
    stored = str(row.get("credential_hash") or "")
    assert stored
    assert issued.credential not in stored
    assert stored != issued.credential


def test_the_audit_trail_records_the_event_without_the_secret(issued):
    device_identity_service.create_device_session(issued.key_id, issued.credential)

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_type, metadata::text
            FROM device_credential_events
            WHERE credential_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (str(issued.credential_id),),
        )
        rows = cur.fetchall()

    assert rows, "issuing and using a credential left no audit trail"
    recorded = " ".join(str(row["metadata"]) for row in rows)
    assert issued.credential not in recorded, "the audit trail carries the raw credential"
    assert {"device_credential_issued", "device_session_issued"} & {str(row["event_type"]) for row in rows}
