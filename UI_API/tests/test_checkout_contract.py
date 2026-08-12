from uuid import uuid4

import pytest
from modules.checkout_confirmation.module import CheckoutConfirmationModule, CheckoutError

from models.commercial_scope import CommercialScope


class Cart:
    def get(self, *, scope, session_id):
        return {"status": "open", "revision": 3, "lines": [{"item_id": "coffee", "quantity": 1}]}


class Pricing:
    def price(self, *, scope, session_id, lines):
        return {"subtotal": 80, "total": 80, "currency": "TWD"}


class Fulfillment:
    def validate(self, *, scope, lines):
        return []


class Store:
    def __init__(self):
        self.prepared = None
        self.confirmed = None

    def prepare(self, **values):
        self.prepared = values
        return {"quote_id": "quote-1", "lines": values["lines"], "total": 80}

    def outcome(self, **values):
        return {"order": self.confirmed} if self.confirmed else {"lines": [{"item_id": "coffee", "quantity": 1}]}

    def confirm(self, **values):
        self.confirmed = {"order_id": "order-1", "total": 80}
        return {"type": "confirmed", "order": self.confirmed, "replayed": False}

    def pending_outbox(self, *, limit):
        return []

    def mark_outbox_published(self, *, event_id):
        raise AssertionError("not used in this contract")


def module():
    return CheckoutConfirmationModule(store=Store(), cart=Cart(), pricing=Pricing(), fulfillment=Fulfillment())


def test_prepare_and_confirm_preserve_scope_and_idempotent_replay():
    store = Store()
    checkout = CheckoutConfirmationModule(store=store, cart=Cart(), pricing=Pricing(), fulfillment=Fulfillment())
    scope = CommercialScope(uuid4(), uuid4(), uuid4())
    quote = checkout.prepare(scope=scope, session_id="session-1")
    assert quote["quote_id"] == "quote-1"
    assert store.prepared["scope"] == scope
    first = checkout.confirm(scope=scope, quote_id="quote-1", idempotency_key="idem-1")
    replay = checkout.confirm(scope=scope, quote_id="quote-1", idempotency_key="idem-1")
    assert first["order"]["order_id"] == "order-1"
    assert replay["replayed"] is True


def test_prepare_rejects_empty_cart_before_pricing_or_order_mutation():
    class EmptyCart:
        def get(self, *, scope, session_id):
            return {"status": "open", "revision": 1, "lines": []}

    checkout = CheckoutConfirmationModule(store=Store(), cart=EmptyCart(), pricing=Pricing(), fulfillment=Fulfillment())
    with pytest.raises(CheckoutError, match="cart_not_ready"):
        checkout.prepare(scope=CommercialScope(uuid4(), uuid4()), session_id="session-1")
