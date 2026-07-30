import json
from uuid import uuid4

import pytest
from modules.cart import CartError, CartModule, SQLiteCartStore
from modules.checkout_confirmation import CheckoutConfirmationModule, CheckoutError, SQLiteCheckoutStore

from models.commercial_scope import CommercialScope


class Pricing:
    def price(self, *, scope, session_id, lines):
        return {"total": sum(row["quantity"] * 100 for row in lines), "currency": "TWD"}


class Fulfillment:
    unavailable = []

    def validate(self, *, scope, lines):
        return list(self.unavailable)


def setup(tmp_path):
    path = tmp_path / "ordering.sqlite3"
    cart = CartModule(SQLiteCartStore(path))
    fulfillment = Fulfillment()
    checkout = CheckoutConfirmationModule(
        store=SQLiteCheckoutStore(path), cart=cart, pricing=Pricing(), fulfillment=fulfillment
    )
    return CommercialScope(uuid4(), uuid4()), cart, checkout, fulfillment


def test_prepare_is_stable_for_revision_and_confirm_is_atomic_and_idempotent(tmp_path):
    scope, cart, checkout, _ = setup(tmp_path)
    cart.replace(scope=scope, session_id="s1", expected_revision=0, lines=[{"item_id": "fries", "quantity": 2}])
    first = checkout.prepare(scope=scope, session_id="s1")
    second = checkout.prepare(scope=scope, session_id="s1")
    assert first["quote_id"] == second["quote_id"]
    confirmed = checkout.confirm(scope=scope, quote_id=first["quote_id"], idempotency_key="key-1")
    replayed = checkout.confirm(scope=scope, quote_id=first["quote_id"], idempotency_key="key-1")
    assert confirmed["type"] == "confirmed" and confirmed["order"]["status"] == "payment_pending"
    assert confirmed["order"]["pickup_number"] == 1
    assert replayed["order"]["order_id"] == confirmed["order"]["order_id"]
    assert replayed["order"]["pickup_number"] == confirmed["order"]["pickup_number"]
    with pytest.raises(CartError, match="cart_closed"):
        cart.replace(scope=scope, session_id="s1", expected_revision=1, lines=[])


def test_cart_mutation_makes_quote_stale_and_unavailable_creates_no_order(tmp_path):
    scope, cart, checkout, fulfillment = setup(tmp_path)
    cart.replace(scope=scope, session_id="s1", expected_revision=0, lines=[{"item_id": "fries", "quantity": 1}])
    quote = checkout.prepare(scope=scope, session_id="s1")
    cart.replace(scope=scope, session_id="s1", expected_revision=1, lines=[{"item_id": "fries", "quantity": 2}])
    assert checkout.confirm(scope=scope, quote_id=quote["quote_id"], idempotency_key="stale")["type"] == "quote_stale"
    fresh = checkout.prepare(scope=scope, session_id="s1")
    fulfillment.unavailable = [{"item_id": "fries", "reason": "sold_out"}]
    result = checkout.confirm(scope=scope, quote_id=fresh["quote_id"], idempotency_key="unavailable")
    assert result == {"type": "items_unavailable", "items": fulfillment.unavailable}
    assert "order" not in checkout.outcome(scope=scope, quote_id=fresh["quote_id"], idempotency_key="")


def test_idempotency_key_cannot_be_reused_for_another_quote(tmp_path):
    scope, cart, checkout, _ = setup(tmp_path)
    cart.replace(scope=scope, session_id="a", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])
    cart.replace(scope=scope, session_id="b", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])
    one = checkout.prepare(scope=scope, session_id="a")
    two = checkout.prepare(scope=scope, session_id="b")
    checkout.confirm(scope=scope, quote_id=one["quote_id"], idempotency_key="same")
    with pytest.raises(CheckoutError, match="idempotency_conflict"):
        checkout.confirm(scope=scope, quote_id=two["quote_id"], idempotency_key="same")


def test_post_commit_consumer_failure_never_obscures_confirmed_order(tmp_path):
    scope, cart, checkout, _ = setup(tmp_path)
    cart.replace(scope=scope, session_id="s1", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])
    quote = checkout.prepare(scope=scope, session_id="s1")
    confirmed = checkout.confirm(scope=scope, quote_id=quote["quote_id"], idempotency_key="key")

    dispatched = checkout.dispatch_outbox(consumer=lambda _event: (_ for _ in ()).throw(RuntimeError("offline")))

    assert dispatched["failed_event_ids"]
    assert (
        checkout.outcome(scope=scope, quote_id=quote["quote_id"], idempotency_key="key")["order"]["order_id"]
        == confirmed["order"]["order_id"]
    )


def test_pickup_number_is_monotonic_per_store_and_scoped_by_store(tmp_path):
    scope, cart, checkout, _ = setup(tmp_path)
    other_store_scope = CommercialScope(scope.tenant_id, uuid4())

    cart.replace(scope=scope, session_id="store-a-1", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])
    cart.replace(scope=scope, session_id="store-a-2", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])
    cart.replace(scope=other_store_scope, session_id="store-b-1", expected_revision=0, lines=[{"item_id": "x", "quantity": 1}])

    first = checkout.prepare(scope=scope, session_id="store-a-1")
    second = checkout.prepare(scope=scope, session_id="store-a-2")
    other_store = checkout.prepare(scope=other_store_scope, session_id="store-b-1")

    assert checkout.confirm(scope=scope, quote_id=first["quote_id"], idempotency_key="a-1")["order"]["pickup_number"] == 1
    assert checkout.confirm(scope=scope, quote_id=second["quote_id"], idempotency_key="a-2")["order"]["pickup_number"] == 2
    assert checkout.confirm(scope=other_store_scope, quote_id=other_store["quote_id"], idempotency_key="b-1")["order"]["pickup_number"] == 1


def test_postgres_adapter_serialises_jsonb_parameters():
    """JSONB 欄位讀回來是 dict，確認訂單時會原樣寫回 confirmed_orders。

    psycopg 無法綁定 dict（cannot adapt type 'dict'），因此 Postgres adapter
    必須在送出前序列化，否則 POST /api/checkout/confirm 會 500。
    """
    from modules.checkout_confirmation.postgres_store import _Conn

    captured = {}

    class FakeCursor:
        def execute(self, query, parameters):
            captured["query"] = query
            captured["parameters"] = parameters
            return self

    conn = _Conn(FakeCursor())
    conn.execute(
        "INSERT INTO confirmed_orders VALUES(?,?,?)",
        ("order-1", {"total": 120, "cart_items": [{"id": "MCD001"}]}, [{"item_id": "MCD001"}]),
    )

    assert captured["query"] == "INSERT INTO confirmed_orders VALUES(%s,%s,%s)"
    order_id, pricing, lines = captured["parameters"]
    assert order_id == "order-1"
    assert isinstance(pricing, str) and json.loads(pricing)["total"] == 120
    assert isinstance(lines, str) and json.loads(lines)[0]["item_id"] == "MCD001"
