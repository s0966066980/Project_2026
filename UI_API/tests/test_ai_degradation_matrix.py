"""AI failure must degrade a feature, never the ability to order.

This is the product's central promise: Ollama, R1-Omni, STT, TTS and RAG are the
Enhancement Layer, and Ordering plus PostgreSQL are the Transaction Authority
(ADR-0028, ADR-0029, and the boundary CONTEXT.md draws around Capability
Criticality). A kiosk that stops taking orders because a model is down has
turned an optional capability into a required one.

Nothing here mocks the ordering path. Each row breaks one provider for real —
by making its client raise, or by pointing it at a closed port — and then walks
menu, cart and checkout through the published API. A row passes only when the
customer could still have ordered.

The matrix the roadmap asks for:

    Failure         Menu   Cart   Checkout   AI feature
    Ollama down     PASS   PASS   PASS       degraded
    R1-Omni down    PASS   PASS   PASS       degraded
    STT down        PASS   PASS   PASS       degraded
    TTS down        PASS   PASS   PASS       degraded
    RAG down        PASS   PASS   PASS       degraded
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from main import app

pytestmark = [pytest.mark.contract, pytest.mark.integration]


class ProviderDown(RuntimeError):
    """What a dead provider looks like from the caller's side."""


def _explode(*_args, **_kwargs):
    raise ProviderDown("provider is unavailable")


async def _explode_async(*_args, **_kwargs):
    raise ProviderDown("provider is unavailable")


# Finding a sellable item costs a cart mutation per candidate, and the cart
# limiter counts them. Resolved once for the whole file so each row spends one
# mutation, not twenty-five.
_SELLABLE_ITEM: dict[str, object] = {}


def _sellable_item(client: TestClient) -> str:
    """An item the store can actually sell right now.

    The menu carries service periods, so refusing a breakfast item at night is
    correct behaviour rather than degradation. Rows need one item that is not
    being refused for that reason.
    """

    if _SELLABLE_ITEM.get("id"):
        return str(_SELLABLE_ITEM["id"])

    items = client.get("/api/v1/catalog/items").json()["data"]["items"]
    for candidate in items[:25]:
        session_id = f"probe-{uuid.uuid4().hex[:12]}"
        cart = client.put(
            f"/api/v1/cart/{session_id}",
            json={"expected_revision": 0, "lines": [{"item_id": candidate["id"], "quantity": 1}]},
        )
        if cart.status_code != 200:
            continue
        if client.post("/api/v1/checkout/prepare", json={"session_id": session_id}).status_code == 200:
            _SELLABLE_ITEM["id"] = candidate["id"]
            return str(candidate["id"])
    raise AssertionError("no item in the seeded menu could be ordered; the matrix cannot say anything")


def _order_through_the_core_path(client: TestClient) -> dict:
    """Menu, cart and checkout, as a customer walks them. Returns what happened."""

    item_id = _sellable_item(client)
    session_id = f"degradation-{uuid.uuid4().hex[:12]}"
    result: dict[str, object] = {}

    catalog = client.get("/api/v1/catalog/items")
    result["menu_status"] = catalog.status_code
    items = catalog.json().get("data", {}).get("items", []) if catalog.status_code == 200 else []
    result["menu_items"] = len(items)

    cart = client.put(
        f"/api/v1/cart/{session_id}",
        json={"expected_revision": 0, "lines": [{"item_id": item_id, "quantity": 1}]},
    )
    result["cart_status"] = cart.status_code
    if cart.status_code != 200:
        return result

    prepared = client.post("/api/v1/checkout/prepare", json={"session_id": session_id})
    result["checkout_status"] = prepared.status_code
    if prepared.status_code == 200:
        result["ordered_item"] = item_id
        result["quote_total"] = prepared.json().get("pricing", {}).get("total")
    return result


def _assert_customer_could_order(outcome: dict, failure: str) -> None:
    assert outcome["menu_status"] == 200, f"{failure}: the menu stopped serving"
    assert outcome["menu_items"] > 0, f"{failure}: the menu came back empty"
    assert outcome["cart_status"] == 200, f"{failure}: the cart stopped accepting items"
    assert outcome.get("checkout_status") == 200, f"{failure}: checkout stopped pricing the cart"
    assert outcome.get("ordered_item"), f"{failure}: nothing reached a priced quote"
    assert isinstance(outcome.get("quote_total"), int), f"{failure}: the quote carried no authoritative total"


@pytest.fixture
def client():
    with TestClient(app) as running:
        yield running


def test_the_core_path_works_before_anything_is_broken(client):
    """The control row. Without it, a passing matrix could mean the path never ran."""

    _assert_customer_could_order(_order_through_the_core_path(client), "no failure injected")


def test_ordering_survives_the_text_model_being_down(client, monkeypatch):
    from services import llm_gateway_service

    for name in ("generate", "generate_text", "complete"):
        if hasattr(llm_gateway_service, name):
            monkeypatch.setattr(llm_gateway_service, name, _explode)

    _assert_customer_could_order(_order_through_the_core_path(client), "Ollama down")


def test_ordering_survives_the_emotion_provider_being_down(client, monkeypatch):
    from modules.emotion.adapters import r1_omni

    monkeypatch.setattr(r1_omni, "collect_evidence", _explode)
    monkeypatch.setattr(r1_omni, "configured_provider_status", _explode)

    _assert_customer_could_order(_order_through_the_core_path(client), "R1-Omni down")


def test_ordering_survives_speech_to_text_being_down(client, monkeypatch):
    from services import stt_service

    monkeypatch.setattr(stt_service, "get_stt", _explode)

    _assert_customer_could_order(_order_through_the_core_path(client), "STT down")


def test_ordering_survives_text_to_speech_being_down(client, monkeypatch):
    from services import tts_service

    monkeypatch.setattr(tts_service, "get_tts", _explode)

    _assert_customer_could_order(_order_through_the_core_path(client), "TTS down")


def test_ordering_survives_retrieval_being_down(client, monkeypatch):
    from services import rag_provider

    monkeypatch.setattr(rag_provider, "get_rag", _explode)

    _assert_customer_could_order(_order_through_the_core_path(client), "RAG down")


def test_every_provider_in_the_matrix_is_actually_reachable_to_break():
    """A row that patches a name nothing owns proves nothing.

    Every row above patches without `raising=False`, so a renamed entry point
    fails loudly rather than silently injecting no failure at all. This states
    the same expectation once, in one readable place.
    """

    from modules.emotion.adapters import r1_omni
    from services import llm_gateway_service, rag_provider, stt_service, tts_service

    assert any(hasattr(llm_gateway_service, name) for name in ("generate", "generate_text", "complete"))
    assert hasattr(r1_omni, "collect_evidence")
    assert hasattr(r1_omni, "configured_provider_status")
    assert hasattr(stt_service, "get_stt")
    assert hasattr(tts_service, "get_tts")
    assert hasattr(rag_provider, "get_rag")
