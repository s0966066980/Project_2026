"""Order aggregate states and transition policy."""

from __future__ import annotations

from enum import Enum


class OrderStatus(str, Enum):
    DRAFT = "draft"
    PRICING = "pricing"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    PREPARING = "preparing"
    COMPLETED = "completed"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    FAILED = "failed"


class InvalidOrderTransitionError(ValueError):
    pass


ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.DRAFT: frozenset({OrderStatus.PRICING, OrderStatus.CANCELLED, OrderStatus.FAILED}),
    OrderStatus.PRICING: frozenset({OrderStatus.PENDING_CONFIRMATION, OrderStatus.CANCELLED, OrderStatus.FAILED}),
    OrderStatus.PENDING_CONFIRMATION: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED, OrderStatus.FAILED}),
    OrderStatus.CONFIRMED: frozenset(
        {OrderStatus.PAYMENT_PENDING, OrderStatus.PREPARING, OrderStatus.CANCEL_PENDING, OrderStatus.FAILED}
    ),
    OrderStatus.PAYMENT_PENDING: frozenset(
        {OrderStatus.PAID, OrderStatus.CANCEL_PENDING, OrderStatus.CANCELLED, OrderStatus.FAILED}
    ),
    OrderStatus.PAID: frozenset({OrderStatus.PREPARING, OrderStatus.CANCEL_PENDING, OrderStatus.FAILED}),
    OrderStatus.PREPARING: frozenset({OrderStatus.COMPLETED, OrderStatus.CANCEL_PENDING, OrderStatus.FAILED}),
    OrderStatus.CANCEL_PENDING: frozenset({OrderStatus.CANCELLED, OrderStatus.PREPARING, OrderStatus.FAILED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.FAILED: frozenset(),
}


def transition_order_status(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    if target not in ALLOWED_ORDER_TRANSITIONS[current]:
        raise InvalidOrderTransitionError(f"Order transition {current.value} -> {target.value} is not allowed")
    return target
