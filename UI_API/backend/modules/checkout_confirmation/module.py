from __future__ import annotations

import logging
from typing import Any, Protocol

from models.commercial_scope import CommercialScope
from modules.operations import _observability as observability_service

_logger = logging.getLogger(observability_service.LOGGER_NAME)


class CheckoutError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class CheckoutStore(Protocol):
    def prepare(self, **values) -> dict[str, Any]: ...
    def confirm(self, **values) -> dict[str, Any]: ...
    def outcome(self, **values) -> dict[str, Any]: ...
    def pending_outbox(self, *, limit: int) -> list[dict[str, Any]]: ...
    def mark_outbox_published(self, *, event_id: str) -> None: ...
    def mark_outbox_failed(
        self, *, event_id: str, safe_error: str, retryable: bool = True
    ) -> dict[str, Any] | None: ...


class Pricing(Protocol):
    def price(self, *, scope: CommercialScope, lines: list[dict[str, Any]]) -> dict[str, Any]: ...


class Fulfillment(Protocol):
    def validate(self, *, scope: CommercialScope, lines: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class CheckoutConfirmationModule:
    def __init__(
        self, *, store: CheckoutStore, cart, pricing: Pricing, fulfillment: Fulfillment, quote_ttl_seconds: int = 300
    ):
        self._store, self._cart, self._pricing, self._fulfillment = store, cart, pricing, fulfillment
        self._quote_ttl_seconds = quote_ttl_seconds

    def prepare(self, *, scope: CommercialScope, session_id: str) -> dict[str, Any]:
        cart = self._cart.get(scope=scope, session_id=session_id)
        if cart["status"] != "open" or not cart["lines"]:
            raise CheckoutError("cart_not_ready")
        pricing = self._pricing.price(scope=scope, session_id=session_id, lines=cart["lines"])
        return self._store.prepare(
            scope=scope,
            session_id=session_id,
            cart_revision=cart["revision"],
            lines=cart["lines"],
            pricing=pricing,
            ttl_seconds=self._quote_ttl_seconds,
        )

    def confirm(self, *, scope: CommercialScope, quote_id: str, idempotency_key: str) -> dict[str, Any]:
        if not quote_id or not idempotency_key:
            raise CheckoutError("invalid_confirmation_identity")
        quote = self._store.outcome(scope=scope, quote_id=quote_id, idempotency_key="")
        if quote.get("order"):
            return {"type": "confirmed", "order": quote["order"], "replayed": True}
        unavailable = self._fulfillment.validate(scope=scope, lines=quote.get("lines") or [])
        return self._store.confirm(
            scope=scope, quote_id=quote_id, idempotency_key=idempotency_key, unavailable=unavailable
        )

    def outcome(self, *, scope: CommercialScope, quote_id: str, idempotency_key: str) -> dict[str, Any]:
        return self._store.outcome(scope=scope, quote_id=quote_id, idempotency_key=idempotency_key)

    def dispatch_outbox(self, *, consumer, limit: int = 100) -> dict[str, Any]:
        completed, failed, dead_lettered = [], [], []
        for event in self._store.pending_outbox(limit=limit):
            try:
                consumer(event)
                self._store.mark_outbox_published(event_id=event["event_id"])
                completed.append(event["event_id"])
            except Exception as exc:
                # A failed event stays unpublished and is retried on the next dispatch, but that
                # retry is bounded and visible. A dead-lettered event never blocks later orders.
                _logger.exception(
                    "checkout_outbox_dispatch_failed",
                    extra={
                        "event_id": event.get("event_id"),
                        "event_type": event.get("event_type"),
                        "safe_error": str(exc)[:200],
                    },
                )
                observability_service.increment_metric("checkout_outbox_dispatch_failed_total")
                result = self._store.mark_outbox_failed(
                    event_id=event["event_id"],
                    safe_error=str(exc)[:200],
                    retryable=True,
                )
                if result and result.get("dead_lettered_at") is not None:
                    dead_lettered.append(event["event_id"])
                else:
                    failed.append(event["event_id"])
        return {
            "published_event_ids": completed,
            "failed_event_ids": failed,
            "dead_lettered_event_ids": dead_lettered,
        }
