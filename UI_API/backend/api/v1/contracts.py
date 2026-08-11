"""Typed API DTOs shared by the `/api/v1` transport layer."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

T = TypeVar("T")


class ApiMeta(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"request_id": "req_0123456789abcdef", "timestamp": "2026-07-13T12:00:00Z"}]}
    )

    request_id: str = Field(pattern=r"^req_[A-Za-z0-9]+$")
    timestamp: datetime


class ApiResponse(BaseModel, Generic[T]):
    data: T
    meta: ApiMeta


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class PaginatedResponse(ApiResponse[list[T]], Generic[T]):
    pagination: PaginationMeta


class ValidationIssue(BaseModel):
    location: list[str | int]
    message: str
    type: str


class ApiError(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "request_id": "req_0123456789abcdef",
                    "details": [],
                }
            ]
        }
    )

    code: str
    message: str
    request_id: str
    details: list[ValidationIssue] = Field(default_factory=list)


class ApiErrorResponse(BaseModel):
    error: ApiError
    meta: ApiMeta


class AdminPrincipalDTO(BaseModel):
    user_id: UUID
    tenant_id: UUID
    allowed_store_ids: list[UUID]
    roles: list[str]
    permissions: list[str]
    session_id: UUID | None = None
    auth_method: str


class CommercialContextDTO(BaseModel):
    tenant_id: UUID
    store_id: UUID
    device_id: UUID | None = None
    principal_type: Literal["admin", "device"]


class MemberSummaryDTO(BaseModel):
    member_id: UUID
    member_ref: str
    phone_masked: str
    nickname: str
    visit_count: int = Field(ge=0)
    total_spend: int = Field(ge=0)
    created_at: datetime | None = None


class OrderSummaryDTO(BaseModel):
    order_id: UUID
    status: str
    currency: str
    total: int = Field(ge=0)
    created_at: datetime
    member_id: UUID | None = None


class PromotionSummaryDTO(BaseModel):
    offer_id: str
    title: str
    status: str
    enabled: bool


class CartQuoteItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=100)
    quantity: int = Field(default=1, ge=1, le=20)
    options: list[dict[str, JsonValue]] = Field(default_factory=list)
    applied_offer_id: str = Field(default="", max_length=100)
    price: JsonValue | None = None
    total: JsonValue | None = None


class CartQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_items: list[CartQuoteItemRequest] = Field(min_length=1, max_length=100)
    session_id: str = Field(default="", max_length=160)


class CartQuoteLineDTO(BaseModel):
    item_id: str
    name: str
    category: str
    quantity: int = Field(ge=1)
    base_unit_price: int = Field(ge=0)
    effective_unit_price: int = Field(ge=0)
    option_unit_total: int = Field(ge=0)
    discount_unit_total: int = Field(ge=0)
    activity_id: str = ""
    activity_name: str = ""


class CartQuoteDTO(BaseModel):
    items: list[CartQuoteLineDTO]
    subtotal: int = Field(ge=0)
    option_total: int = Field(ge=0)
    discount_total: int = Field(ge=0)
    tax_total: int = Field(ge=0)
    total: int = Field(ge=0)
    currency: str
    quote_version: str


class MenuPriceProjectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_item_ids: list[str] = Field(default_factory=list, max_length=100)
    session_id: str = Field(default="", max_length=160)


class MenuPriceProjectionDTO(BaseModel):
    item_id: str
    base_price: int = Field(ge=0)
    effective_price: int = Field(ge=0)
    discount: int = Field(ge=0)
    activity_id: str = ""
    activity_name: str = ""
    conditional: bool = False
    conditional_price: int | None = Field(default=None, ge=0)
    required_cart_item_ids: list[str] = Field(default_factory=list)


class RecommendationEventDTO(BaseModel):
    event_id: str
    event_type: str
    session_id: str
    item_id: str
    item_name: str = ""
    surface: str = ""
    source: str = ""
    audience: str = "guest"
    offer_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    experiment_id: str = ""
    variant_id: str = ""
    strategy: str = ""
    timestamp: datetime | None = None


class CommercialTouchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=140)
    event_type: str = Field(min_length=1, max_length=80)
    decision_id: str = Field(default="", max_length=140)
    impression_id: str = Field(default="", max_length=140)
    campaign_id: str = Field(default="", max_length=120)
    campaign_version: int | None = Field(default=None, ge=1)
    placement: str = Field(default="", max_length=80)
    item_id: str = Field(default="", max_length=100)
    session_id: str = Field(default="", max_length=160)
    strategy: str = Field(default="", max_length=100)
    strategy_version: str = Field(default="", max_length=100)
    experiment_id: str = Field(default="", max_length=100)
    variant_id: str = Field(default="", max_length=100)
    audience: str = Field(default="guest", max_length=40)
    fallback_status: str = Field(default="", max_length=80)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: str = Field(default="", max_length=60)


class CommercialTouchReceiptDTO(BaseModel):
    event_id: str
    accepted: bool
    duplicate: bool
    data_quality: str


class EffectivenessBreakdownDTO(BaseModel):
    variant_id: str
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    add_to_carts: int = Field(ge=0)


class RecommendationEffectivenessDTO(BaseModel):
    filters: dict[str, str]
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    add_to_carts: int = Field(ge=0)
    purchases: int = Field(ge=0)
    ignored: int = Field(ge=0)
    click_through_rate: float = Field(ge=0)
    add_to_cart_rate: float = Field(ge=0)
    purchase_rate: float = Field(ge=0)
    ignore_rate: float = Field(ge=0)
    attributed_revenue: int = Field(ge=0)
    attributed_discount: int = Field(ge=0)
    provisional_attributions: int = Field(ge=0)
    incomplete_events: int = Field(ge=0)
    sample_warning: str
    breakdowns: list[EffectivenessBreakdownDTO]
    comparisons: list[dict[str, JsonValue]]


class AuditRecordDTO(BaseModel):
    audit_id: str
    actor: str
    action: str
    target_type: str
    target_id: str
    created_at: datetime | None = None


class SettingsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, JsonValue]


class SettingsPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, JsonValue]
    expected_version: int | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)


class AvailabilityPutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    reason: str = Field(default="", max_length=200)
    idempotency_key: str | None = Field(default=None, max_length=200)


class AvailabilityDTO(BaseModel):
    item_id: str
    available: bool
    reason: str = ""


class PromotionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offer_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    enabled: bool = True
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


class CampaignScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starts_at: str = Field(default="", max_length=60)
    ends_at: str = Field(default="", max_length=60)


class CampaignPromotionRuleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_item_price", "add_on_fixed_price"]
    item_ids: list[str] = Field(min_length=1, max_length=50)
    required_cart_item_ids: list[str] = Field(default_factory=list, max_length=50)
    promotion_price: int = Field(gt=0, le=999_999)


class CampaignCreativeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    badge: str = Field(default="", max_length=80)
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=240)
    cta: str = Field(default="立即查看", max_length=40)
    theme: Literal["gold", "red", "dark", "simple"] = "gold"


class CampaignDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    objective: Literal["promote_item", "increase_add_on", "increase_order_value", "member_return", "clear_inventory"]
    audience: Literal["all", "member"] = "all"
    schedule: CampaignScheduleRequest
    promotion_rules: list[CampaignPromotionRuleRequest] = Field(min_length=1, max_length=1)
    placements: list[
        Literal["menu_card", "item_detail", "pos_home_banner", "kiosk_cart_banner", "recommendation", "voice"]
    ] = Field(min_length=1, max_length=6)
    creatives: CampaignCreativeRequest = Field(default_factory=CampaignCreativeRequest)


class CampaignDraftUpdateRequest(CampaignDraftRequest):
    expected_version: int = Field(ge=1)


class CampaignPreviewRequest(CampaignDraftRequest):
    campaign_id: str = Field(default="", max_length=120)


class CampaignPublishRequest(CampaignDraftRequest):
    """Publishing an existing campaign carries its id and version; a new one carries neither."""

    campaign_id: str = Field(default="", max_length=120)
    expected_version: int = Field(default=0, ge=0)


class CampaignTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: Literal["draft", "review", "scheduled", "active", "paused", "ended", "archived"]
    expected_version: int = Field(ge=1)


class CampaignSnapshotDTO(BaseModel):
    campaign_id: str
    version: int = Field(ge=1)
    status: str
    payload: dict[str, JsonValue]


class CampaignPreviewDTO(BaseModel):
    valid: bool
    field_errors: list[dict[str, str]]
    conflicts: list[dict[str, str]]
    impact_count: int = Field(ge=0)
    summary: str
    price_previews: list[dict[str, JsonValue]]


class RagDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(default="", max_length=120)
    content: str = Field(min_length=1, max_length=200_000)
    source: str = Field(default="api", max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=200)


RagKnowledgeCategory = Literal[
    "store_and_hours",
    "menu_and_products",
    "promotions",
    "payment_and_invoice",
    "membership",
    "order_and_pickup",
    "delivery",
    "nutrition_and_allergens",
    "other",
]
RagContentType = Literal[
    "knowledge_article",
    "question_answer",
    "policy_rule",
    "operating_procedure",
]
RagRetrievalMethod = Literal["bm25", "dense", "hybrid_rrf", "hybrid_reranker"]


class RagKnowledgeUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: RagKnowledgeCategory
    content_type: RagContentType
    title: str = Field(default="", max_length=160)
    content: str = Field(min_length=1, max_length=200_000)
    expected_row_revision: int | None = Field(default=None, ge=1)
    override_near_duplicate: bool = False


class RagKnowledgeActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_row_revision: int = Field(ge=1)


class RagKnowledgePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_ids: list[str] = Field(min_length=1, max_length=500)
    retry_failures_only: bool = False


class RagKnowledgeTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2_000)
    method: RagRetrievalMethod | None = None
    top_k: Literal[3, 5, 10] | None = None
    relevance_policy: Literal["lenient", "balanced", "strict"] | None = None


class RagRetrievalConfigurationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: RagRetrievalMethod = "hybrid_rrf"
    top_k: Literal[3, 5, 10] = 5
    relevance_policy: Literal["lenient", "balanced", "strict"] = "balanced"
    source_version: int | None = Field(default=None, ge=1)


class FleetCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, max_length=64)
    expires_at: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=200)


class FleetCommandDTO(BaseModel):
    command_id: str
    device_id: UUID
    command: str
    status: str


class OrderTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_status: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = Field(default=None, max_length=200)
