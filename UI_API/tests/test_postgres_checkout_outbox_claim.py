"""The PostgreSQL checkout outbox reports the state it actually claimed."""

import os
import uuid
from datetime import datetime, timezone

import pytest

from modules.checkout_confirmation.postgres_store import PostgresCheckoutStore
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="checkout outbox authority lives in PostgreSQL",
    )
)


def test_postgres_checkout_claim_returns_incremented_attempt_count():
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    tenant_id = uuid.UUID("00000000-0000-4000-8000-000000000001")
    store_id = uuid.UUID("00000000-0000-4000-8000-000000000002")

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO checkout_outbox (
                tenant_id, store_id, event_id, event_type, aggregate_id,
                payload_json, created_at, published_at, available_at,
                attempt_count, max_attempts, last_error
            ) VALUES (%s, %s, %s, 'OrderConfirmed', %s, %s, %s, NULL, %s, 0, 5, '')
            """,
            (tenant_id, store_id, event_id, str(uuid.uuid4()), '{"order_id":"test"}', now, now),
        )
        conn.commit()

    try:
        claimed = PostgresCheckoutStore().pending_outbox(limit=500)
        event = next(item for item in claimed if item["event_id"] == event_id)
        assert event["attempt_count"] == 1
        assert event["max_attempts"] == 5
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM checkout_outbox WHERE event_id = %s", (event_id,))
            conn.commit()
