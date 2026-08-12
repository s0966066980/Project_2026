from __future__ import annotations

from threading import Lock
from uuid import UUID

from capabilities import catalog
from modules.cart import CartModule, PostgresCartStore, SQLiteCartStore
from modules.runtime_persistence.runtime import sqlite_database_path

import config
from models.commercial_scope import LEGACY_DEFAULT_DEVICE_ID, CommercialScope
from repositories import postgres_utils
from services import checkout_pricing_service, member_service

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
            submitted, [], is_member=bool(member_service.get_session_member(session_id, scope)), scope=scope
        )


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

    return module.dispatch_outbox(consumer=consume, limit=limit)
