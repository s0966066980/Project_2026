"""The sole published Campaign/Promotion application surface."""

from capabilities.campaign_promotion.contracts import *  # noqa: F401,F403
from capabilities.campaign_promotion.contracts import CampaignStateError
from modules.promotion import (
    CampaignConflictError,
    PromotionContext,
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


class _PromotionServiceProxy:
    """Compatibility adapter for the remaining versioned promotion DTO calls."""

    def __getattr__(self, name: str):
        from services import promotion_service

        return getattr(promotion_service, name)


promotion_service = _PromotionServiceProxy()


class _CampaignServiceProxy:
    def __init__(self, module_name: str):
        self._module_name = module_name

    def __getattr__(self, name: str):
        import importlib

        return getattr(importlib.import_module(self._module_name), name)


promotion_banner_service = _CampaignServiceProxy("services.promotion_banner_service")
push_copy_service = _CampaignServiceProxy("services.push_copy_service")
push_copy_authoring_service = _CampaignServiceProxy("services.push_copy_authoring_service")
rag_guard_service = _CampaignServiceProxy("services.rag_guard_service")
rag_offer_service = _CampaignServiceProxy("services.rag_offer_service")
push_copy_batch_repository = _CampaignServiceProxy("repositories.push_copy_batch_repository")
push_copy_repository = _CampaignServiceProxy("repositories.push_copy_repository")

__all__ = [
    "CampaignConflictError",
    "CampaignStateError",
    "PromotionContext",
    "create_campaign_draft",
    "evaluate_promotion",
    "get_campaign",
    "list_campaigns",
    "preview_campaign",
    "project_item_price",
    "publish_campaign",
    "quote_promotion",
    "revise_campaign_draft",
    "select_promotion_quote",
    "transition_campaign",
    "promotion_service",
    "promotion_banner_service",
    "push_copy_service",
    "push_copy_authoring_service",
    "rag_guard_service",
    "rag_offer_service",
    "push_copy_batch_repository",
    "push_copy_repository",
]
