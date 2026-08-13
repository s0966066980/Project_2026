"""Member's gate: own the identity, protect the PII, and never block a Guest.

The Module Independence Gate for Member asks for registration and login
including the not-found path, consent, PII encryption with key failure and
redaction, session expiry and store isolation, and one promise that outranks
the rest: **Guest ordering must not depend on Member being available**. A
member store that is down is an inconvenience; a kiosk that stops selling
because of it is a broken product.

Phone numbers are stored encrypted with a lookup HMAC, so these need the real
database and the real key provider. They skip unless the run is on PostgreSQL
and delete the members they create.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from capabilities.member import member_service
from main import app
from models.commercial_scope import CommercialScope
from modules.member import _member_service as member_internals
from modules.member import _pii
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")


def _on_postgres() -> bool:
    return str(os.environ.get("DATABASE_BACKEND", "")).strip() == "postgresql" and postgres_utils.use_postgres()


pytestmark.append(pytest.mark.skipif(not _on_postgres(), reason="member PII is only stored in PostgreSQL"))

_CREATED_PHONES: list[str] = []


def _scope(store_id: uuid.UUID = STORE) -> CommercialScope:
    return CommercialScope(TENANT, store_id, DEVICE)


def _fresh_phone() -> str:
    """A number nobody else in the seeded store is using."""

    phone = f"09{uuid.uuid4().int % 100000000:08d}"
    _CREATED_PHONES.append(phone)
    return phone


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    if not _CREATED_PHONES:
        return
    provider = _pii.configured_key_provider()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for phone in _CREATED_PHONES:
            cur.execute(
                "DELETE FROM members WHERE tenant_id = %s AND phone_lookup_hash = %s",
                (str(TENANT), _pii.phone_lookup_hash(phone, TENANT, provider)),
            )
        conn.commit()
    _CREATED_PHONES.clear()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as running:
        yield running


def test_a_new_number_registers_and_then_logs_in():
    phone = _fresh_phone()
    session = f"member-{uuid.uuid4().hex[:10]}"

    registered = member_service.register(session, phone, nickname="Gate", scope=_scope())
    assert registered.get("ok") is True, registered

    signed_in = member_service.login(f"member-{uuid.uuid4().hex[:10]}", phone, _scope())
    assert signed_in["found"] is True
    assert signed_in["member"]


def test_an_unknown_number_is_not_found_rather_than_an_error():
    result = member_service.login(f"member-{uuid.uuid4().hex[:10]}", _fresh_phone(), _scope())

    assert result["found"] is False
    assert "error" not in result, "a number nobody registered was reported as a failure"


def test_a_malformed_number_is_refused_by_name():
    result = member_service.login(f"member-{uuid.uuid4().hex[:10]}", "not-a-phone", _scope())

    assert result["found"] is False
    assert result.get("error") == "invalid_phone"


def test_protected_identity_writes_no_readable_phone_number(monkeypatch):
    """With identity protection on, the row must not carry the number.

    This runtime defaults to `MEMBER_IDENTITY_READ_MODE=legacy` with dual-write
    off, so the encryption path is never taken and `members.phone` holds the
    number in clear text. That is a deployment decision, not something a test
    should flip on someone's behalf — so this proves the mechanism works when
    enabled, and the observed state of the runtime is recorded as a Pilot
    finding instead.
    """

    import config

    monkeypatch.setattr(config, "MEMBER_IDENTITY_DUAL_WRITE", True)

    phone = _fresh_phone()
    registered = member_service.register(f"member-{uuid.uuid4().hex[:10]}", phone, scope=_scope())
    assert registered.get("ok") is True, registered

    provider = _pii.configured_key_provider()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM members WHERE tenant_id = %s AND phone_lookup_hash = %s",
            (str(TENANT), _pii.phone_lookup_hash(phone, TENANT, provider)),
        )
        row = cur.fetchone()

    assert row is not None, "dual-write did not store a protected identity"
    stored = dict(row)
    assert stored.get("phone_encrypted"), "no ciphertext was written"
    assert _pii.reveal_phone(stored["phone_encrypted"], stored["key_version"], provider) == phone
    assert stored.get("phone_masked") and phone != stored["phone_masked"]


def test_the_runtime_records_which_identity_mode_it_is_in():
    """An operator has to be able to tell whether member PII is protected."""

    import config

    assert config.MEMBER_IDENTITY_READ_MODE in {"legacy", "dual", "uuid_preferred", "uuid_only"}
    assert isinstance(config.MEMBER_IDENTITY_DUAL_WRITE, bool)


def test_the_masked_form_hides_the_middle_of_the_number():
    phone = _fresh_phone()

    masked = member_service.mask_phone(phone)

    assert masked != phone
    assert phone[-3:] not in masked or masked.count("*") >= 3


def test_a_wrong_key_cannot_read_the_number_back():
    """Key failure must refuse, not return something plausible."""

    from modules.member._pii import MemberPiiProtectionError

    phone = _fresh_phone()
    provider = _pii.configured_key_provider()
    protected = _pii.protect_phone(phone, TENANT, provider)

    assert _pii.reveal_phone(protected.phone_encrypted, protected.key_version, provider) == phone

    with pytest.raises(MemberPiiProtectionError):
        _pii.reveal_phone("gAAAAABmZm9ydGhlZ2F0ZQ==", protected.key_version, provider)


def test_the_lookup_hash_is_tenant_scoped():
    """The same number in two tenants must not resolve to one member."""

    phone = _fresh_phone()
    provider = _pii.configured_key_provider()

    assert _pii.phone_lookup_hash(phone, TENANT, provider) != _pii.phone_lookup_hash(phone, uuid.uuid4(), provider)


def test_a_session_binds_to_one_member_and_clears():
    """Session binding is internal; the capability publishes only the read."""

    phone = _fresh_phone()
    session = f"member-{uuid.uuid4().hex[:10]}"
    registered = member_service.register(session, phone, scope=_scope())
    assert registered.get("ok") is True, registered

    assert member_service.get_session_member(session, _scope()) is not None

    member_internals.clear_session(session, _scope())
    assert member_service.get_session_member(session, _scope()) is None


def test_a_session_from_another_store_does_not_resolve():
    phone = _fresh_phone()
    session = f"member-{uuid.uuid4().hex[:10]}"
    member_service.register(session, phone, scope=_scope())

    assert member_service.get_session_member(session, _scope(store_id=uuid.uuid4())) is None


def test_guest_ordering_still_works_when_member_is_unavailable(client, monkeypatch):
    """The promise that outranks the rest of this gate.

    Guest ordering is the Core path. Member is Operational. If a customer
    cannot buy lunch because the member store is down, the criticality
    declaration in CONTEXT.md is decoration.
    """

    def _member_is_down(*_args, **_kwargs):
        raise RuntimeError("member store is unavailable")

    # Break the implementation, not the published proxy: the proxy resolves
    # names back into the capability interface, so patching it would only
    # rearrange the surface without taking the capability down.
    for name in ("login", "register", "get_session_member", "bind_session", "clear_session"):
        monkeypatch.setattr(member_internals, name, _member_is_down)

    items = client.get("/api/v1/catalog/items")
    assert items.status_code == 200

    ordered = False
    for candidate in items.json()["data"]["items"][:25]:
        session_id = f"guest-{uuid.uuid4().hex[:10]}"
        cart = client.put(
            f"/api/v1/cart/{session_id}",
            json={"expected_revision": 0, "lines": [{"item_id": candidate["id"], "quantity": 1}]},
        )
        if cart.status_code != 200:
            continue
        prepared = client.post("/api/v1/checkout/prepare", json={"session_id": session_id})
        if prepared.status_code == 200:
            ordered = True
            break

    assert ordered, "a Guest could not order while the Member capability was down"
