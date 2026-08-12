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
    promotion_service,
    publish_campaign,
    quote_promotion,
    revise_campaign_draft,
    select_promotion_quote,
    transition_campaign,
)

# The promotion rules used to be reached by a call-time import into services/,
# which is what kept this capability on the frozen legacy-layer list. They now
# live in modules/promotion and are published directly.


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
