"""Payment / POS port contracts. No card PAN/CVV storage."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID


class PaymentStatus(str, Enum):
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PaymentRequest:
    order_id: UUID
    amount: int
    currency: str
    provider_token: str
    idempotency_key: str
    tenant_id: UUID
    store_id: UUID


@dataclass(frozen=True)
class PaymentResult:
    provider: str
    status: PaymentStatus
    provider_reference: str
    amount: int
    currency: str
    safe_error: str = ""


@dataclass(frozen=True)
class WebhookEvent:
    provider: str
    event_id: str
    signature_valid: bool
    amount: int
    currency: str
    provider_reference: str
    status: PaymentStatus


class PaymentPort(Protocol):
    def authorize(self, request: PaymentRequest) -> PaymentResult: ...

    def capture(self, provider_reference: str, *, amount: int, currency: str) -> PaymentResult: ...

    def cancel(self, provider_reference: str) -> PaymentResult: ...

    def refund(self, provider_reference: str, *, amount: int, currency: str) -> PaymentResult: ...

    def status(self, provider_reference: str) -> PaymentResult: ...
