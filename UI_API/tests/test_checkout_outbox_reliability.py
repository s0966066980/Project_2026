"""The active Checkout confirmation outbox must retry and dead-letter safely."""

from datetime import datetime, timezone

import pytest

from modules.checkout_confirmation.module import CheckoutConfirmationModule
from modules.checkout_confirmation.sqlite_store import SQLiteCheckoutStore

pytestmark = pytest.mark.unit


def _store_with_event(tmp_path, *, max_attempts=5):
    store = SQLiteCheckoutStore(tmp_path / "checkout.sqlite")
    now = datetime.now(timezone.utc).isoformat()
    with store.tx() as conn:
        conn.execute(
            """
            INSERT INTO checkout_outbox (
                tenant_id, store_id, event_id, event_type, aggregate_id,
                payload_json, created_at, published_at, available_at, max_attempts
            ) VALUES (?, ?, ?, 'OrderConfirmed', ?, ?, ?, NULL, ?, ?)
            """,
            ("tenant", "store", "event-1", "order-1", '{"order_id":"order-1"}', now, now, max_attempts),
        )
    return store


def test_checkout_outbox_failure_is_backed_off_and_reclaimed_after_lock_expires(tmp_path):
    store = _store_with_event(tmp_path)

    first = store.pending_outbox(limit=1)
    assert [event["event_id"] for event in first] == ["event-1"]
    assert first[0]["attempt_count"] == 1
    assert store.pending_outbox(limit=1) == []

    failed = store.mark_outbox_failed(event_id="event-1", safe_error="temporary failure")
    assert failed is not None
    assert failed["dead_lettered_at"] is None
    assert failed["available_at"] > failed["created_at"]

    with store.tx() as conn:
        conn.execute(
            "UPDATE checkout_outbox SET available_at=? WHERE event_id=?",
            (datetime.now(timezone.utc).isoformat(), "event-1"),
        )
    reclaimed = store.pending_outbox(limit=1)
    assert reclaimed[0]["attempt_count"] == 2


def test_checkout_dispatch_dead_letters_after_attempt_budget(tmp_path):
    store = _store_with_event(tmp_path, max_attempts=1)
    module = CheckoutConfirmationModule(store=store, cart=None, pricing=None, fulfillment=None)

    result = module.dispatch_outbox(consumer=lambda _event: (_ for _ in ()).throw(RuntimeError("provider down")))

    assert result["published_event_ids"] == []
    assert result["failed_event_ids"] == []
    assert result["dead_lettered_event_ids"] == ["event-1"]
    assert store.pending_outbox(limit=1) == []


def test_published_checkout_outbox_clears_lease_and_is_not_delivered_again(tmp_path):
    store = _store_with_event(tmp_path)
    assert store.pending_outbox(limit=1)

    store.mark_outbox_published(event_id="event-1")

    assert store.pending_outbox(limit=1) == []
    with store._connect() as conn:
        row = conn.execute(
            "SELECT published_at, locked_by, locked_until, last_error FROM checkout_outbox WHERE event_id=?",
            ("event-1",),
        ).fetchone()
    assert row["published_at"] is not None
    assert row["locked_by"] is None
    assert row["locked_until"] is None
    assert row["last_error"] == ""
