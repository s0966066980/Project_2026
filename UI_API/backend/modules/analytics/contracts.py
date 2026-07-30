"""Typed contracts for commercial touch collection."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TouchReceipt:
    event_id: str
    accepted: bool
    duplicate: bool
    data_quality: str


@dataclass(frozen=True)
class EffectivenessReport:
    filters: dict[str, str]
    impressions: int
    clicks: int
    add_to_carts: int
    purchases: int
    ignored: int
    click_through_rate: float
    add_to_cart_rate: float
    purchase_rate: float
    ignore_rate: float
    purchase_rate_target: float
    ignore_rate_guardrail: float
    target_status: str
    attributed_revenue: int
    attributed_discount: int
    provisional_attributions: int
    incomplete_events: int
    sample_warning: str
    breakdowns: list[dict[str, Any]]
    comparisons: list[dict[str, Any]]
