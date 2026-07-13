"""Milestone 1G Order state, pricing snapshot, and idempotency contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_order_state_machine_rejects_invalid_transitions() -> None:
    from models.order import InvalidOrderTransitionError, OrderStatus, transition_order_status

    assert transition_order_status(OrderStatus.DRAFT, OrderStatus.PRICING) is OrderStatus.PRICING
    assert transition_order_status(OrderStatus.CONFIRMED, OrderStatus.PAYMENT_PENDING) is OrderStatus.PAYMENT_PENDING
    with pytest.raises(InvalidOrderTransitionError):
        transition_order_status(OrderStatus.DRAFT, OrderStatus.COMPLETED)
    with pytest.raises(InvalidOrderTransitionError):
        transition_order_status(OrderStatus.CANCELLED, OrderStatus.CONFIRMED)


def test_order_migration_defines_transactional_snapshot_and_outbox() -> None:
    sql = (ROOT / "UI_API/backend/schemas/migrations/0007_order_checkout_hardening.sql").read_text(encoding="utf-8")
    for fragment in (
        "CREATE TABLE orders",
        "CREATE TABLE order_items",
        "CREATE TABLE order_promotion_usages",
        "CREATE TABLE order_outcomes",
        "CREATE TABLE order_outbox",
        "idempotency_key",
        "request_fingerprint",
        "calculation_version",
        "currency",
        "UNIQUE (tenant_id, store_id, idempotency_key)",
    ):
        assert fragment in sql
    assert "CREATE EXTENSION" not in sql.upper()


def test_pricing_returns_historical_snapshot_and_ignores_client_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    from services import checkout_pricing_service

    monkeypatch.setattr(
        checkout_pricing_service.menu_repository,
        "get_menu",
        lambda: [{"id": "meal", "name": "Meal", "category": "main", "price": 120}],
    )
    priced = checkout_pricing_service.price_checkout_cart(
        [{"id": "meal", "quantity": 2, "price": 1, "total": 1}],
        ["meal"],
        is_member=False,
    )
    assert priced["subtotal"] == 240
    assert priced["discount_total"] == 0
    assert priced["tax_total"] == 0
    assert priced["total"] == 240
    assert priced["currency"] == "TWD"
    assert priced["calculation_version"]
    assert priced["cart_items"][0]["base_unit_price"] == 120
    assert priced["cart_items"][0]["final_unit_price"] == 120


def test_checkout_request_fingerprint_is_deterministic_and_excludes_pii() -> None:
    from services.checkout_service import checkout_request_fingerprint

    first = checkout_request_fingerprint(
        "session-a",
        {"cart_items": [{"id": "meal", "quantity": 1}], "total": 120, "currency": "TWD"},
    )
    second = checkout_request_fingerprint(
        "session-a",
        {"currency": "TWD", "total": 120, "cart_items": [{"quantity": 1, "id": "meal"}]},
    )
    assert first == second
    assert "session-a" not in first
    assert "meal" not in first


def test_idempotency_conflict_is_a_shared_safe_error() -> None:
    from repositories.checkout_order_repository import CheckoutIdempotencyConflictError

    error = CheckoutIdempotencyConflictError("same key was used for another request")
    assert "request" in str(error)
    assert not hasattr(error, "payload")
