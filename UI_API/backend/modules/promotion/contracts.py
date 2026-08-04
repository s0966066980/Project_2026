"""Typed contracts for promotion eligibility and pricing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from models.commercial_scope import CommercialScope


@dataclass(frozen=True)
class PromotionContext:
    now: datetime
    is_member: bool | None = None
    item_id: str = ""
    category: str = ""
    cart_item_ids: frozenset[str] | None = None
    placement: str = ""
    scope: CommercialScope | None = None


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    code: str


@dataclass(frozen=True)
class PromotionQuote:
    eligible: bool
    code: str
    base_price: int
    effective_price: int
    discount: int
    promotion_ref: str = ""
    promotion_title: str = ""


@dataclass(frozen=True)
class PriceProjection:
    base_price: int
    effective_price: int
    discount: int
    promotion_ref: str = ""
    promotion_title: str = ""
    conditional: bool = False
    conditional_price: int | None = None
    required_cart_item_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CampaignSnapshot:
    campaign_id: str
    version: int
    status: str
    payload: dict


@dataclass(frozen=True)
class CampaignPreview:
    valid: bool
    field_errors: tuple[dict[str, str], ...]
    conflicts: tuple[dict[str, str], ...]
    impact_count: int
    summary: str
    price_previews: tuple[dict, ...] = ()


class CampaignConflictError(ValueError):
    """The requested expected_version no longer matches durable state."""


class CampaignStateError(ValueError):
    """The requested lifecycle transition is not allowed."""
