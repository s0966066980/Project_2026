"""Typed, versioned Admin read contracts with legacy API compatibility."""

# This module intentionally re-exports the compatibility namespace to the
# capability-specific route modules below; unused imports are part of that API.
# ruff: noqa: F401

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Annotated, Literal, Protocol, TypeVar
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Query, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from api.v1.contracts import (
    AdminPrincipalDTO,
    ApiErrorResponse,
    ApiMeta,
    ApiResponse,
    AuditRecordDTO,
    AvailabilityDTO,
    AvailabilityPutRequest,
    CampaignDraftRequest,
    CampaignDraftUpdateRequest,
    CampaignPreviewDTO,
    CampaignPreviewRequest,
    CampaignPublishRequest,
    CampaignSnapshotDTO,
    CampaignTransitionRequest,
    CartQuoteDTO,
    CartQuoteLineDTO,
    CartQuoteRequest,
    CommercialContextDTO,
    CommercialTouchReceiptDTO,
    CommercialTouchRequest,
    FleetCommandDTO,
    FleetCommandRequest,
    MemberSummaryDTO,
    MenuPriceProjectionDTO,
    MenuPriceProjectionRequest,
    OrderSummaryDTO,
    OrderTransitionRequest,
    PaginatedResponse,
    PaginationMeta,
    PromotionCreateRequest,
    PromotionSummaryDTO,
    RagKnowledgeActionRequest,
    RagKnowledgePublishRequest,
    RagKnowledgeTestRequest,
    RagKnowledgeUpsertRequest,
    RagRetrievalConfigurationRequest,
    RecommendationEffectivenessDTO,
    RecommendationEventDTO,
    SettingsDTO,
    SettingsPatchRequest,
)
from capabilities import catalog
from capabilities.campaign_promotion import (
    CampaignConflictError,
    CampaignStateError,
    PromotionContext,
    create_campaign_draft,
    get_campaign,
    list_campaigns,
    preview_campaign,
    project_item_price,
    promotion_service,
    publish_campaign,
    revise_campaign_draft,
    transition_campaign,
)
from capabilities.identity_access import (
    fleet_management_service,
    scope_from_admin_principal,
    scope_from_device_principal,
)
from capabilities.knowledge_rag import (
    PublicationError,
    RetrievalCheckError,
    knowledge_publication_runtime,
    rag_knowledge_service,
    retrieval_check_runtime,
)
from capabilities.member import member_service
from capabilities.operations_configuration import interface as operations
from capabilities.operations_configuration import operations_overview_runtime, service_health_runtime
from capabilities.ordering import checkout_order_repository, checkout_pricing_service
from capabilities.recommendation_analytics import (
    TouchValidationError,
    analytics_pipeline_service,
    build_effectiveness_report,
    record_touch,
)
from capabilities.recommendation_analytics import list_events as list_recommendation_events
from models.commercial_scope import CommercialScope
from models.order import OrderStatus
from realtime import event_bus
from utils.auth_utils import authorize_admin_request, require_kiosk_token

_admin_cookie = APIKeyCookie(name="admin_session", scheme_name="AdminSessionCookie", auto_error=False)
_admin_bearer = HTTPBearer(scheme_name="BearerAuth", auto_error=False)
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
SortOrder = Annotated[Literal["asc", "desc"], Query()]
T = TypeVar("T")


def _document_admin_security(
    _cookie: Annotated[str | None, Security(_admin_cookie)] = None,
    _bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_admin_bearer)] = None,
) -> None:
    """Declare supported credentials; authorization remains in the shared server policy."""


def _meta(request: Request) -> ApiMeta:
    return ApiMeta(request_id=str(request.state.request_id), timestamp=datetime.now(timezone.utc))


def _scope(request: Request, permission: str) -> CommercialScope:
    principal = authorize_admin_request(request, permission)
    scope = scope_from_admin_principal(principal)
    request.state.commercial_scope = scope
    request.state.admin_principal = principal
    return scope


async def _autopublish(request: Request, scope: CommercialScope, item_id: str) -> dict:
    """儲存後立刻排入發布。

    知識寫完就是要給顧客用的，不該再回列表勾選一次；草稿只是索引完成前的過渡狀態，
    不再是操作者要管理的東西（見 ADR-0017）。發布權限不足時仍保留內容，只是留在未發布狀態，
    並明確說出原因，而不是假裝成功。
    """

    principal = getattr(request.state, "admin_principal", None)
    has_permission = getattr(principal, "has_permission", None)
    if callable(has_permission) and not has_permission("rag.publish"):
        return {"published": False, "reason": "missing_publish_permission"}
    try:
        await asyncio.to_thread(
            knowledge_publication_runtime.default_module().request_publication,
            scope=scope,
            item_ids=[item_id],
            actor=_admin_actor(request),
            retry_failures_only=False,
        )
    except PublicationError as exc:
        # 內容已經存下來了；發布失敗不該讓整個儲存動作看起來失敗。
        return {"published": False, "reason": str(getattr(exc, "code", "") or exc)}
    return {"published": True, "reason": ""}


def _page(rows: list[T], page: int, page_size: int) -> tuple[list[T], PaginationMeta]:
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], PaginationMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


def _member_uuid(value: object, scope: CommercialScope) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return uuid5(scope.tenant_id, f"legacy-member:{value}")


def _optional_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _campaign_dto(snapshot) -> CampaignSnapshotDTO:
    return CampaignSnapshotDTO(
        campaign_id=snapshot.campaign_id,
        version=snapshot.version,
        status=snapshot.status,
        payload=snapshot.payload,
    )


def _admin_actor(request: Request) -> str:
    return str(getattr(getattr(request.state, "admin_principal", None), "user_id", "admin"))


class CapabilityError(Protocol):
    """The shape every capability error carries into an HTTP response.

    The knowledge rules moved into their capability's module, so the cycle that
    first blocked re-exporting these error classes is gone — but a production
    route may not import a module directly either. The contract these handlers
    actually rely on is the two attributes below.
    """

    code: str
    details: dict


def _rag_http_error(exc: CapabilityError) -> HTTPException:
    status = (
        409
        if isinstance(exc, rag_knowledge_service.RagKnowledgeConflictError)
        or exc.code in {"exact_duplicate", "near_duplicate"}
        else 422
    )
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "details": exc.details},
    )


def _retrieval_check_http_error(exc: RetrievalCheckError) -> HTTPException:
    status = 404 if exc.code == "retrieval_check_not_found" else 409
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "details": exc.details},
    )


def _publication_http_error(exc: PublicationError) -> HTTPException:
    status = (
        409
        if exc.code
        in {
            "exact_duplicate",
            "near_duplicate",
            "stale_knowledge_item",
            "publication_in_progress",
        }
        else 422
    )
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "details": exc.details},
    )


async def _publish_campaign_change(snapshot) -> None:
    await event_bus.publish_event(
        {
            "type": "campaigns_changed",
            "session_id": "",
            "payload": {
                "campaign_id": snapshot.campaign_id,
                "version": snapshot.version,
                "status": snapshot.status,
            },
        }
    )


# Explicit re-export list. This was a `globals()` comprehension, which Python
# evaluates fine but mypy cannot, so every `import *` consumer below reported
# each name as undefined. Keep this list in step with the imports above.
__all__ = [
    "annotations",
    "asyncio",
    "math",
    "datetime",
    "timezone",
    "Annotated",
    "Literal",
    "TypeVar",
    "UUID",
    "uuid5",
    "catalog",
    "CapabilityError",
    "CampaignConflictError",
    "CampaignStateError",
    "PromotionContext",
    "create_campaign_draft",
    "get_campaign",
    "list_campaigns",
    "preview_campaign",
    "project_item_price",
    "promotion_service",
    "publish_campaign",
    "revise_campaign_draft",
    "transition_campaign",
    "fleet_management_service",
    "scope_from_admin_principal",
    "scope_from_device_principal",
    "PublicationError",
    "RetrievalCheckError",
    "knowledge_publication_runtime",
    "rag_knowledge_service",
    "retrieval_check_runtime",
    "member_service",
    "operations",
    "operations_overview_runtime",
    "service_health_runtime",
    "checkout_order_repository",
    "checkout_pricing_service",
    "TouchValidationError",
    "analytics_pipeline_service",
    "build_effectiveness_report",
    "record_touch",
    "list_recommendation_events",
    "APIRouter",
    "HTTPException",
    "Query",
    "Request",
    "Security",
    "APIKeyCookie",
    "HTTPAuthorizationCredentials",
    "HTTPBearer",
    "event_bus",
    "AdminPrincipalDTO",
    "ApiErrorResponse",
    "ApiMeta",
    "ApiResponse",
    "AuditRecordDTO",
    "AvailabilityDTO",
    "AvailabilityPutRequest",
    "CampaignDraftRequest",
    "CampaignDraftUpdateRequest",
    "CampaignPreviewDTO",
    "CampaignPreviewRequest",
    "CampaignPublishRequest",
    "CampaignSnapshotDTO",
    "CampaignTransitionRequest",
    "CartQuoteDTO",
    "CartQuoteLineDTO",
    "CartQuoteRequest",
    "CommercialContextDTO",
    "CommercialTouchReceiptDTO",
    "CommercialTouchRequest",
    "FleetCommandDTO",
    "FleetCommandRequest",
    "MemberSummaryDTO",
    "MenuPriceProjectionDTO",
    "MenuPriceProjectionRequest",
    "OrderSummaryDTO",
    "OrderTransitionRequest",
    "PaginatedResponse",
    "PaginationMeta",
    "PromotionCreateRequest",
    "PromotionSummaryDTO",
    "RagKnowledgeActionRequest",
    "RagKnowledgePublishRequest",
    "RagKnowledgeTestRequest",
    "RagKnowledgeUpsertRequest",
    "RagRetrievalConfigurationRequest",
    "RecommendationEffectivenessDTO",
    "RecommendationEventDTO",
    "SettingsDTO",
    "SettingsPatchRequest",
    "CommercialScope",
    "OrderStatus",
    "authorize_admin_request",
    "require_kiosk_token",
    "_admin_cookie",
    "_admin_bearer",
    "Page",
    "PageSize",
    "SortOrder",
    "T",
    "_document_admin_security",
    "_meta",
    "_scope",
    "_autopublish",
    "_page",
    "_member_uuid",
    "_optional_datetime",
    "_campaign_dto",
    "_admin_actor",
    "_rag_http_error",
    "_retrieval_check_http_error",
    "_publication_http_error",
    "_publish_campaign_change",
]
