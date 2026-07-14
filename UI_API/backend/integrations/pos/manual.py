"""Manual POS adapter — pending_manual_entry only, never fake ACK."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class ManualPOSResult:
    status: str
    provider_reference: str
    message: str


class ManualPOSAdapter:
    name = "manual"

    def submit_order(self, *, order_ref: str, payload: dict | None = None) -> ManualPOSResult:
        return ManualPOSResult(
            status="pending_manual_entry",
            provider_reference=f"pos-manual-{uuid4().hex[:12]}",
            message=f"Enter order {order_ref} on POS manually",
        )

    def acknowledge(self, *, provider_reference: str) -> ManualPOSResult:
        return ManualPOSResult(
            status="pending_manual_entry",
            provider_reference=provider_reference,
            message="Manual POS entry not auto-acknowledged",
        )
