"""Promotion data contracts used by services and route responses."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PosPromotionBannerItem(BaseModel):
    id: str
    badge: str = ""
    title: str
    subtitle: str = ""
    description: str = ""
    original_price: int | None = None
    promo_price: int | None = None
    save_text: str = ""
    start_at: str = ""
    end_at: str = ""
    cta_text: str = ""
    target_type: str = "none"
    target_value: str = ""
    theme: str = "gold"
    legal_text: str = ""
    rotation_seconds: int = 6
    member_only: bool = False
    item_ids: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    required_cart_item_ids: list[str] = Field(default_factory=list)


class PosPromotionBannerResponse(BaseModel):
    items: list[PosPromotionBannerItem] = Field(default_factory=list)
