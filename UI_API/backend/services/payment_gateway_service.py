"""Payment/POS gateway with fake adapter, webhook verification, and reconciliation."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from models.payment import PaymentPort, PaymentRequest, PaymentResult, PaymentStatus, WebhookEvent
from services import observability_service


class PaymentGatewayError(ValueError):
    pass


@dataclass
class FakePaymentAdapter:
    """In-memory sandbox adapter. Never stores card PAN/CVV."""

    name: str = "fake_pos"
    _records: dict[str, PaymentResult] = field(default_factory=dict)
    _idempotency: dict[str, PaymentResult] = field(default_factory=dict)

    def authorize(self, request: PaymentRequest) -> PaymentResult:
        if "card_number" in request.provider_token or "cvv" in request.provider_token.casefold():
            raise PaymentGatewayError("card_data_not_allowed")
        if request.idempotency_key in self._idempotency:
            return self._idempotency[request.idempotency_key]
        reference = f"pay_{uuid4().hex[:12]}"
        result = PaymentResult(
            provider=self.name,
            status=PaymentStatus.AUTHORIZED,
            provider_reference=reference,
            amount=request.amount,
            currency=request.currency,
        )
        self._records[reference] = result
        self._idempotency[request.idempotency_key] = result
        return result

    def capture(self, provider_reference: str, *, amount: int, currency: str) -> PaymentResult:
        current = self._records.get(provider_reference)
        if current is None:
            return PaymentResult(self.name, PaymentStatus.FAILED, provider_reference, amount, currency, "not_found")
        if current.amount != amount or current.currency != currency:
            return PaymentResult(
                self.name, PaymentStatus.FAILED, provider_reference, amount, currency, "amount_mismatch"
            )
        result = PaymentResult(self.name, PaymentStatus.CAPTURED, provider_reference, amount, currency)
        self._records[provider_reference] = result
        return result

    def cancel(self, provider_reference: str) -> PaymentResult:
        current = self._records.get(provider_reference)
        if current is None:
            return PaymentResult(self.name, PaymentStatus.FAILED, provider_reference, 0, "", "not_found")
        result = PaymentResult(self.name, PaymentStatus.CANCELLED, provider_reference, current.amount, current.currency)
        self._records[provider_reference] = result
        return result

    def refund(self, provider_reference: str, *, amount: int, currency: str) -> PaymentResult:
        current = self._records.get(provider_reference)
        if current is None or current.status is not PaymentStatus.CAPTURED:
            return PaymentResult(
                self.name, PaymentStatus.FAILED, provider_reference, amount, currency, "not_refundable"
            )
        result = PaymentResult(self.name, PaymentStatus.REFUNDED, provider_reference, amount, currency)
        self._records[provider_reference] = result
        return result

    def status(self, provider_reference: str) -> PaymentResult:
        return self._records.get(
            provider_reference,
            PaymentResult(self.name, PaymentStatus.UNKNOWN, provider_reference, 0, "", "not_found"),
        )


_DEFAULT = FakePaymentAdapter()
_PROCESSED_WEBHOOKS: set[str] = set()


def get_adapter() -> PaymentPort:
    return _DEFAULT


def authorize(request: PaymentRequest, *, adapter: PaymentPort | None = None) -> PaymentResult:
    active = adapter or get_adapter()
    result = active.authorize(request)
    observability_service.increment_metric("checkout_attempts_total", status=f"payment_{result.status.value}")
    return result


def verify_webhook(
    *,
    payload: bytes,
    signature_header: str,
    shared_secret: str,
    event_id: str,
    amount: int,
    currency: str,
    provider_reference: str,
    status: PaymentStatus,
    expected_amount: int,
    expected_currency: str,
) -> WebhookEvent:
    if not shared_secret:
        raise PaymentGatewayError("webhook_secret_missing")
    digest = hmac.new(shared_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    valid = hmac.compare_digest(digest, str(signature_header or ""))
    if not valid:
        raise PaymentGatewayError("invalid_webhook_signature")
    if amount != expected_amount or currency != expected_currency:
        raise PaymentGatewayError("webhook_amount_mismatch")
    if event_id in _PROCESSED_WEBHOOKS:
        # Replay protection: treat as already processed success path.
        return WebhookEvent("fake_pos", event_id, True, amount, currency, provider_reference, status)
    _PROCESSED_WEBHOOKS.add(event_id)
    return WebhookEvent("fake_pos", event_id, True, amount, currency, provider_reference, status)


def reconcile(
    internal_rows: list[dict[str, Any]],
    provider_rows: list[dict[str, Any]],
) -> dict[str, list[str]]:
    internal = {str(row["provider_reference"]): row for row in internal_rows}
    provider = {str(row["provider_reference"]): row for row in provider_rows}
    missing_internal = sorted(set(provider) - set(internal))
    missing_provider = sorted(set(internal) - set(provider))
    amount_mismatch = sorted(
        key
        for key in set(internal) & set(provider)
        if int(internal[key].get("amount") or 0) != int(provider[key].get("amount") or 0)
        or str(internal[key].get("currency")) != str(provider[key].get("currency"))
    )
    return {
        "missing_internal": missing_internal,
        "missing_provider": missing_provider,
        "amount_mismatch": amount_mismatch,
    }


def reset_for_tests() -> None:
    global _DEFAULT, _PROCESSED_WEBHOOKS
    _DEFAULT = FakePaymentAdapter()
    _PROCESSED_WEBHOOKS = set()
