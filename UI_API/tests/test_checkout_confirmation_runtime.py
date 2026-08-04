"""The dispatch_outbox consumer must rebuild the confirming device's CommercialScope so
member_orders.origin_device_id (NOT NULL, FK to devices) never gets written as null.

This is a regression test for a bug where every completed order silently vanished from a
member's order history: the outbox event never carried device_id, so the consumer reconstructed
a device-less scope and every write to member_orders failed its NOT NULL constraint. The failure
was swallowed by the outbox's own retry semantics, so nothing but Postgres itself ever saw it.
"""

from uuid import uuid4

from models.commercial_scope import LEGACY_DEFAULT_DEVICE_ID


def test_consume_uses_the_devices_id_carried_on_the_event(monkeypatch):
    from modules.checkout_confirmation import runtime

    tenant_id, store_id, device_id = uuid4(), uuid4(), uuid4()
    order = {"session_id": "s1", "lines": [{"item_id": "x"}], "pricing": {"total": 100}}
    event = {
        "event_type": "OrderConfirmed",
        "tenant_id": str(tenant_id),
        "store_id": str(store_id),
        "payload": {"quote_id": "q1", "device_id": str(device_id)},
    }

    class FakeModule:
        def outcome(self, *, scope, quote_id, idempotency_key):
            captured_scopes.append(scope)
            return {"order": order}

        def dispatch_outbox(self, *, consumer, limit=100):
            consumer(event)
            return {"published_event_ids": [], "failed_event_ids": []}

    captured_scopes = []
    finalize_calls = []
    monkeypatch.setattr(runtime, "default_module", lambda: FakeModule())
    monkeypatch.setattr(
        runtime.member_service,
        "finalize_checkout",
        lambda *args: finalize_calls.append(args),
    )

    runtime.dispatch_outbox()

    assert captured_scopes[0].device_id == device_id
    assert finalize_calls[0][-1].device_id == device_id


def test_consume_falls_back_to_the_legacy_device_for_events_queued_before_this_fix(monkeypatch):
    """Events already sitting in the outbox before device_id was added to the payload must
    still drain instead of failing forever."""
    from modules.checkout_confirmation import runtime

    tenant_id, store_id = uuid4(), uuid4()
    order = {"session_id": "s1", "lines": [], "pricing": {"total": 0}}
    event = {
        "event_type": "OrderConfirmed",
        "tenant_id": str(tenant_id),
        "store_id": str(store_id),
        "payload": {"quote_id": "q1"},  # no device_id, as pre-fix events look
    }

    class FakeModule:
        def outcome(self, *, scope, quote_id, idempotency_key):
            captured_scopes.append(scope)
            return {"order": order}

        def dispatch_outbox(self, *, consumer, limit=100):
            consumer(event)
            return {"published_event_ids": [], "failed_event_ids": []}

    captured_scopes = []
    monkeypatch.setattr(runtime, "default_module", lambda: FakeModule())
    monkeypatch.setattr(runtime.member_service, "finalize_checkout", lambda *args: None)

    runtime.dispatch_outbox()

    assert captured_scopes[0].device_id == LEGACY_DEFAULT_DEVICE_ID
