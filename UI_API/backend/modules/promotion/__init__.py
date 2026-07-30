"""Promotion module public interface."""

from modules.promotion.application import (
    create_campaign_draft,
    evaluate_promotion,
    get_campaign,
    list_campaigns,
    preview_campaign,
    project_item_price,
    publish_campaign,
    quote_promotion,
    revise_campaign_draft,
    select_promotion_quote,
    transition_campaign,
)
from modules.promotion.contracts import (
    CampaignConflictError,
    CampaignPreview,
    CampaignSnapshot,
    CampaignStateError,
    EligibilityResult,
    PriceProjection,
    PromotionContext,
    PromotionQuote,
)

__all__ = [
    "EligibilityResult",
    "PromotionContext",
    "PromotionQuote",
    "PriceProjection",
    "CampaignConflictError",
    "CampaignPreview",
    "CampaignSnapshot",
    "CampaignStateError",
    "create_campaign_draft",
    "evaluate_promotion",
    "get_campaign",
    "list_campaigns",
    "quote_promotion",
    "project_item_price",
    "select_promotion_quote",
    "preview_campaign",
    "publish_campaign",
    "revise_campaign_draft",
    "transition_campaign",
]
