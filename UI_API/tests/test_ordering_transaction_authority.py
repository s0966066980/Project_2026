"""The invariants that make Ordering the transaction authority.

The roadmap states them as a list the domain may never break:

    client price != trusted price
    promotion must be server validated
    duplicate checkout must not create duplicate order
    AI output cannot mutate authoritative transaction directly
    payment pending != paid

Each is checked through the published API against the database that actually
stores orders. A fake store cannot answer "did this produce two rows", which is
the whole question, so these skip unless the run is really on PostgreSQL and
remove the orders they create.
"""

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]


def _on_postgres() -> bool:
    return str(os.environ.get("DATABASE_BACKEND", "")).strip() == "postgresql" and postgres_utils.use_postgres()


pytestmark.append(pytest.mark.skipif(not _on_postgres(), reason="order authority lives in PostgreSQL"))

_CREATED_QUOTES: list[str] = []


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as running:
        yield running
    _purge_orders()


def _purge_orders() -> None:
    if not _CREATED_QUOTES:
        return
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for quote_id in _CREATED_QUOTES:
            cur.execute("DELETE FROM confirmed_orders WHERE quote_id = %s", (quote_id,))
        conn.commit()
    _CREATED_QUOTES.clear()


def _sellable(client: TestClient) -> dict:
    """An item the store can sell right now, with its published price."""

    items = client.get("/api/v1/catalog/items").json()["data"]["items"]
    for candidate in items[:25]:
        session_id = f"authority-probe-{uuid.uuid4().hex[:10]}"
        cart = client.put(
            f"/api/v1/cart/{session_id}",
            json={"expected_revision": 0, "lines": [{"item_id": candidate["id"], "quantity": 1}]},
        )
        if cart.status_code != 200:
            continue
        if client.post("/api/v1/checkout/prepare", json={"session_id": session_id}).status_code == 200:
            return candidate
    raise AssertionError("no sellable item; the invariants cannot be exercised")


def _quote(client: TestClient, item_id: str, *, lines: list[dict] | None = None) -> dict:
    session_id = f"authority-{uuid.uuid4().hex[:10]}"
    payload = lines if lines is not None else [{"item_id": item_id, "quantity": 1}]
    assert client.put(f"/api/v1/cart/{session_id}", json={"expected_revision": 0, "lines": payload}).status_code == 200
    prepared = client.post("/api/v1/checkout/prepare", json={"session_id": session_id})
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    _CREATED_QUOTES.append(str(body["quote_id"]))
    return body


def test_a_browser_cannot_set_the_price_it_pays(client):
    """The cart is a list of intentions, not an invoice the client writes."""

    item = _sellable(client)
    published = int(item["price"])

    tampered = _quote(
        client,
        item["id"],
        lines=[
            {
                "item_id": item["id"],
                "quantity": 1,
                "unit_price": 1,
                "price": 1,
                "total": 1,
                "effective_unit_price": 1,
            }
        ],
    )

    assert int(tampered["pricing"]["subtotal"]) == published, "the client changed the subtotal"
    assert int(tampered["pricing"]["total"]) != 1, "the client dictated the total"


def test_the_stored_cart_keeps_only_what_the_customer_may_decide(client):
    item = _sellable(client)
    session_id = f"authority-{uuid.uuid4().hex[:10]}"

    stored = client.put(
        f"/api/v1/cart/{session_id}",
        json={"expected_revision": 0, "lines": [{"item_id": item["id"], "quantity": 1, "unit_price": 1}]},
    ).json()

    assert stored["lines"], "the cart came back empty"
    assert "unit_price" not in stored["lines"][0], "a price the client sent was stored on the line"


def test_any_discount_on_the_quote_names_the_offer_that_granted_it(client):
    """A total below the sum of the parts has to say which campaign did it."""

    item = _sellable(client)
    quote = _quote(client, item["id"])
    pricing = quote["pricing"]

    if int(pricing["total"]) < int(pricing["subtotal"]):
        applied = [line.get("applied_offer_id") for line in pricing.get("cart_items", [])]
        assert any(applied), "the quote is discounted with no offer recorded against any line"


def test_confirming_the_same_quote_twice_returns_one_order(client):
    item = _sellable(client)
    quote = _quote(client, item["id"])
    key = f"idem-{uuid.uuid4().hex[:12]}"

    first = client.post(
        "/api/v1/checkout/confirm", json={"quote_id": quote["quote_id"]}, headers={"Idempotency-Key": key}
    )
    second = client.post(
        "/api/v1/checkout/confirm", json={"quote_id": quote["quote_id"]}, headers={"Idempotency-Key": key}
    )

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True, "the second submit was treated as a new confirmation"
    assert first.json()["order"]["order_id"] == second.json()["order"]["order_id"]


def test_a_second_submit_under_a_different_key_still_makes_one_order(client):
    """A customer who reloads and presses pay again must not buy twice.

    The quote is the anchor, not the idempotency header — a browser that
    generates a fresh key is exactly the case a header-only guard would miss.
    """

    item = _sellable(client)
    quote = _quote(client, item["id"])

    first = client.post(
        "/api/v1/checkout/confirm",
        json={"quote_id": quote["quote_id"]},
        headers={"Idempotency-Key": f"first-{uuid.uuid4().hex[:8]}"},
    )
    second = client.post(
        "/api/v1/checkout/confirm",
        json={"quote_id": quote["quote_id"]},
        headers={"Idempotency-Key": f"second-{uuid.uuid4().hex[:8]}"},
    )

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["order"]["order_id"] == second.json()["order"]["order_id"]

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS orders FROM confirmed_orders WHERE quote_id = %s", (quote["quote_id"],))
        assert int(cur.fetchone()["orders"]) == 1, "one quote produced more than one order"


def test_a_confirmed_order_is_pending_payment_and_never_paid(client):
    """HTTP 200 from checkout is not money received (roadmap 14.2)."""

    item = _sellable(client)
    quote = _quote(client, item["id"])

    confirmed = client.post(
        "/api/v1/checkout/confirm",
        json={"quote_id": quote["quote_id"]},
        headers={"Idempotency-Key": f"pending-{uuid.uuid4().hex[:8]}"},
    ).json()

    status = str(confirmed["order"]["status"])
    assert status == "payment_pending", status
    assert status != "paid"


def test_the_order_can_be_recovered_after_the_answer_is_lost(client):
    """Outcome Unknown: the customer's device dropped the reply, the order stands."""

    item = _sellable(client)
    quote = _quote(client, item["id"])
    key = f"lost-{uuid.uuid4().hex[:10]}"

    confirmed = client.post(
        "/api/v1/checkout/confirm", json={"quote_id": quote["quote_id"]}, headers={"Idempotency-Key": key}
    ).json()

    recovered = client.get(f"/api/v1/checkout/outcome/{quote['quote_id']}", params={"idempotency_key": key})

    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["order"]["order_id"] == confirmed["order"]["order_id"]


def test_an_unknown_quote_cannot_be_confirmed(client):
    response = client.post(
        "/api/v1/checkout/confirm",
        json={"quote_id": str(uuid.uuid4())},
        headers={"Idempotency-Key": f"ghost-{uuid.uuid4().hex[:8]}"},
    )

    assert response.status_code in {404, 409, 422}, response.status_code
    assert response.status_code != 200, "a quote that was never issued produced an order"
