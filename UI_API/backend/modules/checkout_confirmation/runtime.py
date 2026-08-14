from __future__ import annotations

from threading import Lock
from uuid import UUID

import config
from capabilities import catalog
from capabilities.member import member_service
from capabilities.operations_configuration import interface as operations
from models.commercial_scope import LEGACY_DEFAULT_DEVICE_ID, CommercialScope
from modules.cart import CartModule, PostgresCartStore, SQLiteCartStore
from modules.checkout_confirmation import _pricing_service as checkout_pricing_service
from modules.runtime_persistence.runtime import sqlite_database_path
from repositories import postgres_utils

from .module import CheckoutConfirmationModule
from .postgres_store import PostgresCheckoutStore
from .sqlite_store import SQLiteCheckoutStore


class ProductionPricing:
    def price(self, *, scope, session_id, lines):
        submitted = [
            {
                "id": row["item_id"],
                "quantity": row["quantity"],
                "options": row.get("options") or [],
                "applied_offer_id": row.get("applied_offer_id") or "",
            }
            for row in lines
        ]
        return checkout_pricing_service.price_checkout_cart(
            submitted, [], is_member=self._is_member(session_id, scope), scope=scope
        )

    @staticmethod
    def _is_member(session_id, scope) -> bool:
        """Ask Member, and price as a Guest if it cannot answer.

        Ordering is Core and Member is Operational (CONTEXT.md, Capability
        Criticality). Letting a member-store outage propagate out of pricing
        made checkout fail for Guests too, which inverts that declaration —
        an Optional-tier dependency was deciding whether anyone could buy
        anything. Guest pricing is the safe answer: it never applies a member
        discount the customer has not proven they are entitled to.
        """

        try:
            return bool(member_service.get_session_member(session_id, scope))
        except Exception:  # noqa: BLE001 - any Member failure must degrade, not block
            operations.observability_service.increment_metric(
                "checkout_member_lookup_degraded_total", status="unavailable"
            )
            return False


class ProductionFulfillment:
    def validate(self, *, scope, lines):
        menu = {str(row.get("id") or ""): row for row in catalog.list_active_items()}
        return [
            {"item_id": row["item_id"], "reason": "unavailable"}
            for row in lines
            if row["item_id"] not in menu or menu[row["item_id"]].get("available", True) is False
        ]


_MODULE = None
_CART = None
_KEY = ""
_LOCK = Lock()


def _path() -> str:
    return sqlite_database_path()


def default_cart() -> CartModule:
    default_module()
    return _CART


def default_module() -> CheckoutConfirmationModule:
    global _MODULE, _CART, _KEY
    path = _path()
    with _LOCK:
        if _MODULE is None or _KEY != path:
            use_postgres = postgres_utils.use_postgres()
            cart_store = PostgresCartStore() if use_postgres else SQLiteCartStore(path)
            _CART = CartModule(cart_store)
            _MODULE = CheckoutConfirmationModule(
                store=PostgresCheckoutStore() if use_postgres else SQLiteCheckoutStore(path),
                cart=_CART,
                pricing=ProductionPricing(),
                fulfillment=ProductionFulfillment(),
                quote_ttl_seconds=int(config.get("CHECKOUT_QUOTE_TTL_SECONDS", 300)),
            )
            _KEY = path
        return _MODULE


def reset_default_for_tests():
    global _MODULE, _CART, _KEY
    with _LOCK:
        _MODULE = None
        _CART = None
        _KEY = ""


def dispatch_outbox(*, limit: int = 100) -> dict:
    module = default_module()

    def consume(event):
        # These consumers are deliberately post-commit. A failure leaves the
        # event pending and can never change the already-confirmed Order.
        if event["event_type"] != "OrderConfirmed":
            return
        # member_orders.origin_device_id is NOT NULL; events queued before this field existed
        # carry none, so they fall back to the legacy default device rather than fail forever.
        device_id = str(event["payload"].get("device_id") or "").strip()
        scope = CommercialScope(
            UUID(event["tenant_id"]),
            UUID(event["store_id"]),
            UUID(device_id) if device_id else LEGACY_DEFAULT_DEVICE_ID,
        )
        outcome = module.outcome(
            scope=scope,
            quote_id=event["payload"]["quote_id"],
            idempotency_key="",
        )
        order = outcome["order"]
        member_service.finalize_checkout(
            order["session_id"],
            [line["item_id"] for line in order["lines"]],
            int(order["pricing"].get("total") or 0),
            True,
            order["lines"],
            scope,
        )
        _attribute_order_to_touches(scope, order)

    return module.dispatch_outbox(consumer=consume, limit=limit)


def _attribute_order_to_touches(scope: CommercialScope, order: dict) -> None:
    """Close the commercial funnel: say which touch this order belongs to.

    `build_order_attributions` and `upsert_order_touch_attributions_scoped`
    have existed, with tests, since the analytics capability was written. Until
    now nothing in production called either of them, so
    `order_touch_attributions` was empty and "did the recommendation lead to a
    sale" was unanswerable — which is what left the Admin push success rate at
    zero while ten thousand impressions sat in the touch log.

    This runs as an outbox consequence rather than inside `confirm`: an
    attribution is a downstream projection of an order that already exists, and
    ordering must not depend on analytics. A failure here leaves the event
    pending for the next dispatch and never touches the order.
    """

    from capabilities.recommendation_analytics import build_order_attributions, record_touch
    from modules.analytics import _pipeline as analytics_pipeline_service
    from modules.checkout_confirmation.adapters.orders import upsert_order_touch_attributions_scoped

    touches = analytics_pipeline_service.list_events(tenant_id=scope.tenant_id, store_id=scope.store_id)
    session_touches = [
        touch for touch in touches if str(touch.get("session_ref") or "") == str(order.get("session_id") or "")
    ]

    # The purchase itself is a touch. Without it the funnel can show that a
    # recommendation reached a cart but never that the cart was paid for.
    for line in order.get("lines") or []:
        record_touch(
            {
                "event_id": f"purchase_{order['order_id']}_{line.get('order_item_id') or line.get('item_id')}",
                "event_type": "purchase",
                "session_id": order.get("session_id") or "",
                "order_id": order.get("order_id") or "",
                "item_id": str(line.get("item_id") or ""),
                "placement": "checkout",
            },
            scope,
        )

    rows = build_order_attributions(order, session_touches)
    if rows:
        upsert_order_touch_attributions_scoped(scope, rows)
