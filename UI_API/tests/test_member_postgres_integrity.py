"""PostgreSQL integrity evidence for scoped Member registration."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from capabilities.member import member_service
from models.commercial_scope import CommercialScope
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.security]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="member integrity evidence requires PostgreSQL",
    )
)

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")
DEVICE = uuid.UUID("00000000-0000-4000-8000-000000000003")


def test_concurrent_registration_is_one_scoped_member_with_one_preference_row():
    phone = f"09{uuid.uuid4().int % 100000000:08d}"
    scope = CommercialScope(TENANT, STORE, DEVICE)

    def register(session_suffix: str) -> dict:
        return member_service.register(
            f"member-race-{session_suffix}",
            phone,
            nickname="Race",
            order_history_consent=False,
            personalization_consent=False,
            scope=scope,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(register, ("one", "two")))

    try:
        assert all(result.get("ok") is True for result in results), results
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, order_history_consent, personalization_consent "
                "FROM members WHERE tenant_id = %s AND phone = %s",
                (str(TENANT), phone),
            )
            members = cur.fetchall()
            assert len(members) == 1
            member = members[0]
            assert member["order_history_consent"] is False
            assert member["personalization_consent"] is False

            cur.execute("SELECT member_id FROM member_preferences WHERE member_id = %s", (member["id"],))
            assert len(cur.fetchall()) == 1
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM members WHERE tenant_id = %s AND phone = %s",
                (str(TENANT), phone),
            )
            conn.commit()
