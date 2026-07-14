"""Manual payment adapter for single-store pilot — never pretends capture succeeded."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class ManualPaymentResult:
    status: str
    provider_reference: str
    message: str


class ManualPaymentAdapter:
    """Creates a pending manual payment record; no fake capture."""

    name = "manual"

    def authorize(self, *, amount: int, currency: str, order_ref: str) -> ManualPaymentResult:
        return ManualPaymentResult(
            status="pending_manual_payment",
            provider_reference=f"manual-{uuid4().hex[:12]}",
            message=f"Collect {amount} {currency} for order {order_ref} at counter",
        )

    def capture(self, *, provider_reference: str) -> ManualPaymentResult:
        # Explicitly does not capture automatically.
        return ManualPaymentResult(
            status="pending_manual_payment",
            provider_reference=provider_reference,
            message="Manual payment must be confirmed by staff",
        )

    def status(self, *, provider_reference: str) -> ManualPaymentResult:
        return ManualPaymentResult(
            status="pending_manual_payment",
            provider_reference=provider_reference,
            message="Awaiting manual confirmation",
        )
