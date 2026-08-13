"""PostgreSQL evidence for checkout outbox recovery across dispatcher restarts."""

import json
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


def test_postgres_checkout_outbox_reclaims_after_failure_and_publishes_once():
    event_id = str(uuid.uuid4())
    aggregate_id = str(uuid.uuid4())
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
            ) VALUES (%s, %s, %s, 'OrderConfirmed', %s, %s, %s, NULL, %s, 0, 2, '')
            """,
            (tenant_id, store_id, event_id, aggregate_id, json.dumps({"quote_id": "restart-test"}), now, now),
        )
        conn.commit()

    try:
        claimed = PostgresCheckoutStore().pending_outbox(limit=10)
        event = next(item for item in claimed if item["event_id"] == event_id)
        assert event["attempt_count"] == 1

        failed = PostgresCheckoutStore().mark_outbox_failed(
            event_id=event_id,
            safe_error="dispatcher restarted before acknowledgement",
        )
        assert failed is not None
        assert failed["locked_until"] is None
        assert failed["last_error"] == "dispatcher restarted before acknowledgement"

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE checkout_outbox SET available_at = NOW() WHERE event_id = %s",
                (event_id,),
            )
            conn.commit()

        reclaimed = PostgresCheckoutStore().pending_outbox(limit=10)
        event = next(item for item in reclaimed if item["event_id"] == event_id)
        assert event["attempt_count"] == 2

        PostgresCheckoutStore().mark_outbox_published(event_id=event_id)

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT published_at, locked_by, locked_until FROM checkout_outbox WHERE event_id = %s",
                (event_id,),
            )
            stored = cur.fetchone()
        assert stored["published_at"] is not None
        assert stored["locked_by"] is None
        assert stored["locked_until"] is None
        assert PostgresCheckoutStore().pending_outbox(limit=10) == []
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM checkout_outbox WHERE event_id = %s", (event_id,))
            conn.commit()
