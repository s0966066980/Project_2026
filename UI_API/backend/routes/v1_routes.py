"""Typed, versioned Admin read contracts with legacy API compatibility."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Annotated, Literal, TypeVar
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Query, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from modules.analytics import TouchValidationError, build_effectiveness_report, record_touch
from modules.knowledge_publication import PublicationError
from modules.knowledge_publication import runtime as knowledge_publication_runtime
from modules.operations_overview import runtime as operations_overview_runtime
from modules.promotion import (
    CampaignConflictError,
    CampaignStateError,
    PromotionContext,
    create_campaign_draft,
    get_campaign,
    list_campaigns,
    preview_campaign,
    project_item_price,
    publish_campaign,
    revise_campaign_draft,
    transition_campaign,
)
from modules.recommendation import list_events as list_recommendation_events
from modules.retrieval_check import RetrievalCheckError
from modules.retrieval_check import runtime as retrieval_check_runtime
from modules.service_health import runtime as service_health_runtime
from realtime import event_bus

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
    RagDocumentDTO,
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
from models.commercial_scope import CommercialScope
from models.order import OrderStatus
from repositories import availability_repository, checkout_order_repository, commercial_settings_repository
from services import (
    admin_audit_service,
    analytics_pipeline_service,
    checkout_pricing_service,
    fleet_management_service,
    member_service,
    promotion_service,
    rag_knowledge_service,
)
from services.commercial_context_service import scope_from_admin_principal, scope_from_device_principal
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


def _rag_document_dto(asset) -> RagDocumentDTO:
    return RagDocumentDTO(
        document_id=asset.document_id,
        version=asset.version,
        status=asset.status.value,
        checksum=asset.checksum,
        content_ref=asset.content_ref,
    )


def _rag_http_error(exc: rag_knowledge_service.RagKnowledgeError) -> HTTPException:
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


def create_router(_deps: dict | None = None) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1",
        dependencies=[Security(_document_admin_security)],
        responses={
            401: {"model": ApiErrorResponse, "description": "Authentication required"},
            403: {"model": ApiErrorResponse, "description": "Permission denied"},
            422: {"model": ApiErrorResponse, "description": "Request validation failed"},
            500: {"model": ApiErrorResponse, "description": "Safe internal error"},
        },
    )

    @router.get(
        "/auth/me",
        tags=["v1-auth"],
        operation_id="v1_get_current_admin",
        response_model=ApiResponse[AdminPrincipalDTO],
    )
    async def current_admin(request: Request) -> ApiResponse[AdminPrincipalDTO]:
        principal = authorize_admin_request(request, "operations.read")
        return ApiResponse(
            data=AdminPrincipalDTO(
                user_id=principal.user_id,
                tenant_id=principal.tenant_id,
                allowed_store_ids=list(principal.allowed_store_ids),
                roles=list(principal.roles),
                permissions=list(principal.permissions),
                session_id=principal.session_id,
                auth_method=principal.auth_method,
            ),
            meta=_meta(request),
        )

    @router.get(
        "/commercial-context",
        tags=["v1-commercial-context"],
        operation_id="v1_get_commercial_context",
        response_model=ApiResponse[CommercialContextDTO],
    )
    async def commercial_context(request: Request) -> ApiResponse[CommercialContextDTO]:
        principal = authorize_admin_request(request, "operations.read")
        scope = scope_from_admin_principal(principal)
        request.state.commercial_scope = scope
        return ApiResponse(
            data=CommercialContextDTO(
                tenant_id=scope.tenant_id,
                store_id=scope.store_id,
                device_id=scope.device_id,
                principal_type="admin",
            ),
            meta=_meta(request),
        )

    @router.post(
        "/cart/quote",
        tags=["v1-cart"],
        operation_id="v1_quote_cart",
        response_model=ApiResponse[CartQuoteDTO],
    )
    async def quote_cart(request: Request, body: CartQuoteRequest) -> ApiResponse[CartQuoteDTO]:
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        request.state.commercial_scope = scope
        member = None
        if body.session_id:
            member = await asyncio.to_thread(member_service.get_session_member, body.session_id, scope)
        try:
            priced = await asyncio.to_thread(
                checkout_pricing_service.price_checkout_cart,
                [item.model_dump() for item in body.cart_items],
                [item.id for item in body.cart_items],
                is_member=bool(member),
                scope=scope,
            )
        except checkout_pricing_service.CartValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
        return ApiResponse(
            data=CartQuoteDTO(
                items=[
                    CartQuoteLineDTO(
                        item_id=str(item["id"]),
                        name=str(item["name"]),
                        category=str(item.get("category") or ""),
                        quantity=int(item["quantity"]),
                        base_unit_price=int(item["base_unit_price"]),
                        effective_unit_price=int(item["final_unit_price"]),
                        option_unit_total=int(item["option_unit_total"]),
                        discount_unit_total=int(item["discount_unit_total"]),
                        activity_id=str(item.get("applied_offer_id") or ""),
                        activity_name=str(item.get("promotion_title") or ""),
                    )
                    for item in priced["cart_items"]
                ],
                subtotal=int(priced["subtotal"]),
                option_total=int(priced["option_total"]),
                discount_total=int(priced["discount_total"]),
                tax_total=int(priced["tax_total"]),
                total=int(priced["total"]),
                currency=str(priced["currency"]),
                quote_version=str(priced["calculation_version"]),
            ),
            meta=_meta(request),
        )

    @router.post(
        "/menu/price-projection",
        tags=["v1-menu"],
        operation_id="v1_project_menu_prices",
        response_model=ApiResponse[list[MenuPriceProjectionDTO]],
    )
    async def project_menu_prices(
        request: Request,
        body: MenuPriceProjectionRequest,
    ) -> ApiResponse[list[MenuPriceProjectionDTO]]:
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        request.state.commercial_scope = scope
        member = None
        if body.session_id:
            member = await asyncio.to_thread(member_service.get_session_member, body.session_id, scope)
        menu = await asyncio.to_thread(
            checkout_pricing_service.menu_repository.get_menu_scoped, scope, include_retired=False, ensure_seed=True
        )
        promotions = await asyncio.to_thread(promotion_service.list_promotions, scope)
        now = datetime.now(timezone.utc)
        data = []
        for item in menu:
            try:
                base_price = int(float(item.get("price") or 0))
            except (TypeError, ValueError):
                continue
            projection = project_item_price(
                promotions,
                PromotionContext(
                    now=now,
                    is_member=bool(member),
                    item_id=str(item.get("id") or ""),
                    category=str(item.get("category") or ""),
                    cart_item_ids=frozenset(body.cart_item_ids),
                    scope=scope,
                ),
                base_price=base_price,
            )
            data.append(
                MenuPriceProjectionDTO(
                    item_id=str(item.get("id") or ""),
                    base_price=projection.base_price,
                    effective_price=projection.effective_price,
                    discount=projection.discount,
                    activity_id=projection.promotion_ref,
                    activity_name=projection.promotion_title,
                    conditional=projection.conditional,
                    conditional_price=projection.conditional_price,
                    required_cart_item_ids=list(projection.required_cart_item_ids),
                )
            )
        return ApiResponse(data=data, meta=_meta(request))

    @router.post(
        "/commercial-touches",
        tags=["v1-analytics"],
        operation_id="v1_record_commercial_touch",
        response_model=ApiResponse[CommercialTouchReceiptDTO],
    )
    async def record_commercial_touch(
        request: Request,
        body: CommercialTouchRequest,
    ) -> ApiResponse[CommercialTouchReceiptDTO]:
        principal = require_kiosk_token(request)
        scope = scope_from_device_principal(principal)
        request.state.commercial_scope = scope
        try:
            receipt = await asyncio.to_thread(record_touch, body.model_dump(), scope)
        except TouchValidationError as exc:
            raise HTTPException(status_code=422, detail={"code": str(exc), "message": "事件資料無法接受"}) from exc
        return ApiResponse(
            data=CommercialTouchReceiptDTO(
                event_id=receipt.event_id,
                accepted=receipt.accepted,
                duplicate=receipt.duplicate,
                data_quality=receipt.data_quality,
            ),
            meta=_meta(request),
        )

    @router.get(
        "/operations/service-health",
        tags=["v1-analytics"],
        operation_id="v1_get_service_health",
        response_model=ApiResponse[dict],
    )
    async def service_health(request: Request) -> ApiResponse[dict]:
        """Connection status, latency, observation time and a safe error, per service.

        Nothing about the inside of the system: an operator reads this to answer
        whether a customer can order right now.
        """

        _scope(request, "operations.read")
        statuses = await asyncio.to_thread(service_health_runtime.default_module().snapshot)
        return ApiResponse(data={"services": [status.as_dict() for status in statuses]}, meta=_meta(request))

    @router.get(
        "/operations/overview",
        tags=["v1-analytics"],
        operation_id="v1_get_operations_overview",
        response_model=ApiResponse[dict],
    )
    async def operations_overview(
        request: Request,
        days: Annotated[int, Query(ge=1, le=31)] = 1,
    ) -> ApiResponse[dict]:
        """The four counts a store manager reads, each carrying what it means.

        The definitions travel with the values because every one of them excludes
        something a reader would otherwise assume was included.
        """

        scope = _scope(request, "analytics.read")
        overview = await asyncio.to_thread(
            operations_overview_runtime.default_module().build,
            scope=scope,
            since=operations_overview_runtime.since_days_ago(days),
        )
        return ApiResponse(data={**overview.as_dict(), "window_days": days}, meta=_meta(request))

    @router.get(
        "/recommendation-effectiveness",
        tags=["v1-analytics"],
        operation_id="v1_get_recommendation_effectiveness",
        response_model=ApiResponse[RecommendationEffectivenessDTO],
    )
    async def recommendation_effectiveness(
        request: Request,
        since: Annotated[str, Query(max_length=60)] = "",
        until: Annotated[str, Query(max_length=60)] = "",
        placement: Annotated[str, Query(max_length=80)] = "",
        campaign_id: Annotated[str, Query(max_length=120)] = "",
        strategy_version: Annotated[str, Query(max_length=100)] = "",
        variant_id: Annotated[str, Query(max_length=100)] = "",
        audience: Annotated[str, Query(max_length=40)] = "",
    ) -> ApiResponse[RecommendationEffectivenessDTO]:
        scope = _scope(request, "recommendations.effectiveness.read")
        events, attributions, settings_values = await asyncio.gather(
            asyncio.to_thread(
                analytics_pipeline_service.list_events,
                tenant_id=scope.tenant_id,
                store_id=scope.store_id,
                since=since,
                until=until,
            ),
            asyncio.to_thread(
                checkout_order_repository.list_order_touch_attributions_scoped,
                scope,
                since=since,
                until=until,
            ),
            asyncio.to_thread(commercial_settings_repository.get_settings_scoped, scope),
        )
        report = build_effectiveness_report(
            events,
            attributions,
            filters={
                "placement": placement,
                "campaign_id": campaign_id,
                "strategy_version": strategy_version,
                "variant_id": variant_id,
                "audience": audience,
            },
            targets=settings_values,
        )
        return ApiResponse(data=RecommendationEffectivenessDTO(**report.__dict__), meta=_meta(request))

    @router.get(
        "/members",
        tags=["v1-members"],
        operation_id="v1_list_members",
        response_model=PaginatedResponse[MemberSummaryDTO],
    )
    async def members(
        request: Request,
        page: Page = 1,
        page_size: PageSize = 25,
        q: Annotated[str, Query(max_length=120)] = "",
        sort_by: Annotated[Literal["created_at", "nickname", "visit_count", "total_spend"], Query()] = "created_at",
        sort_order: SortOrder = "desc",
    ) -> PaginatedResponse[MemberSummaryDTO]:
        scope = _scope(request, "members.read")
        records, total = await asyncio.to_thread(
            member_service.admin_search,
            q,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            scope=scope,
        )
        mapped = [
            MemberSummaryDTO(
                member_id=_member_uuid(row.get("member_id") or row.get("id"), scope),
                member_ref=str(row.get("member_ref") or ""),
                phone_masked=str(row.get("phone_masked") or ""),
                nickname=str(row.get("nickname") or ""),
                visit_count=int(row.get("visit_count") or 0),
                total_spend=int(row.get("total_spend") or 0),
                created_at=_optional_datetime(row.get("created_at")),
            )
            for row in records
        ]
        data = mapped
        pagination = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=(total + page_size - 1) // page_size if total else 0,
        )
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/orders",
        tags=["v1-orders"],
        operation_id="v1_list_orders",
        response_model=PaginatedResponse[OrderSummaryDTO],
    )
    async def orders(
        request: Request,
        page: Page = 1,
        page_size: PageSize = 25,
        status: Annotated[str, Query(max_length=40)] = "",
        sort_order: SortOrder = "desc",
    ) -> PaginatedResponse[OrderSummaryDTO]:
        scope = _scope(request, "members.read")
        records, total = await asyncio.to_thread(
            checkout_order_repository.list_orders_scoped,
            scope,
            status=status,
            offset=(page - 1) * page_size,
            limit=page_size,
            sort_order=sort_order,
        )
        data = [OrderSummaryDTO(**row) for row in records]
        pagination = PaginationMeta(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        )
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/campaigns",
        tags=["v1-campaigns"],
        operation_id="v1_list_campaigns",
        response_model=ApiResponse[list[CampaignSnapshotDTO]],
    )
    async def campaigns(request: Request) -> ApiResponse[list[CampaignSnapshotDTO]]:
        scope = _scope(request, "campaigns.read")
        rows = await asyncio.to_thread(list_campaigns, scope)
        return ApiResponse(data=[_campaign_dto(row) for row in rows], meta=_meta(request))

    @router.get(
        "/campaigns/{campaign_id}",
        tags=["v1-campaigns"],
        operation_id="v1_get_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_detail(request: Request, campaign_id: str) -> ApiResponse[CampaignSnapshotDTO]:
        scope = _scope(request, "campaigns.read")
        row = await asyncio.to_thread(get_campaign, campaign_id, scope)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"})
        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/preview",
        tags=["v1-campaigns"],
        operation_id="v1_preview_campaign",
        response_model=ApiResponse[CampaignPreviewDTO],
    )
    async def campaign_preview(request: Request, body: CampaignPreviewRequest) -> ApiResponse[CampaignPreviewDTO]:
        scope = _scope(request, "campaigns.read")
        payload = body.model_dump(exclude={"campaign_id"})
        catalog_items = await asyncio.to_thread(
            checkout_pricing_service.menu_repository.get_menu_scoped, scope, include_retired=False, ensure_seed=True
        )
        result = await asyncio.to_thread(
            preview_campaign,
            payload,
            scope,
            exclude_campaign_id=body.campaign_id,
            catalog_items=catalog_items,
        )
        return ApiResponse(data=CampaignPreviewDTO(**result.__dict__), meta=_meta(request))

    @router.post(
        "/campaigns",
        tags=["v1-campaigns"],
        operation_id="v1_create_campaign_draft",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def create_campaign(request: Request, body: CampaignDraftRequest) -> ApiResponse[CampaignSnapshotDTO]:
        scope = _scope(request, "campaigns.write")
        catalog_items = await asyncio.to_thread(
            checkout_pricing_service.menu_repository.get_menu_scoped, scope, include_retired=False, ensure_seed=True
        )
        try:
            row = await asyncio.to_thread(
                create_campaign_draft,
                body.model_dump(),
                scope,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "campaign_invalid", "message": "還有欄位需要修正。", "field_errors": list(exc.args[0])},
            ) from exc
        await _publish_campaign_change(row)
        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.put(
        "/campaigns/{campaign_id}/draft",
        tags=["v1-campaigns"],
        operation_id="v1_revise_campaign_draft",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def revise_campaign(
        request: Request,
        campaign_id: str,
        body: CampaignDraftUpdateRequest,
    ) -> ApiResponse[CampaignSnapshotDTO]:
        scope = _scope(request, "campaigns.write")
        catalog_items = await asyncio.to_thread(
            checkout_pricing_service.menu_repository.get_menu_scoped, scope, include_retired=False, ensure_seed=True
        )
        try:
            row = await asyncio.to_thread(
                revise_campaign_draft,
                campaign_id,
                body.model_dump(exclude={"expected_version"}),
                scope,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )
        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc
        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409, detail={"code": str(exc), "message": "目前活動狀態無法修改。"}
            ) from exc
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "campaign_invalid", "message": "還有欄位需要修正。", "field_errors": list(exc.args[0])},
            ) from exc
        await _publish_campaign_change(row)
        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/publish",
        tags=["v1-campaigns"],
        operation_id="v1_publish_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_publish(request: Request, body: CampaignPublishRequest) -> ApiResponse[CampaignSnapshotDTO]:
        _scope(request, "campaigns.write")
        scope = _scope(request, "campaigns.publish")
        catalog_items = await asyncio.to_thread(
            checkout_pricing_service.menu_repository.get_menu_scoped, scope, include_retired=False, ensure_seed=True
        )
        try:
            row = await asyncio.to_thread(
                publish_campaign,
                body.model_dump(exclude={"campaign_id", "expected_version"}),
                scope,
                campaign_id=body.campaign_id,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
                catalog_items=catalog_items,
            )
        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc
        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409, detail={"code": str(exc), "message": "此活動已經發布，請從活動列表操作暫停或結束。"}
            ) from exc
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "campaign_invalid",
                    "message": "還有欄位需要修正，修正後才能發布。",
                    "field_errors": list(exc.args[0]),
                },
            ) from exc
        await _publish_campaign_change(row)
        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.post(
        "/campaigns/{campaign_id}/transition",
        tags=["v1-campaigns"],
        operation_id="v1_transition_campaign",
        response_model=ApiResponse[CampaignSnapshotDTO],
    )
    async def campaign_transition(
        request: Request,
        campaign_id: str,
        body: CampaignTransitionRequest,
    ) -> ApiResponse[CampaignSnapshotDTO]:
        scope = _scope(request, "campaigns.publish")
        try:
            row = await asyncio.to_thread(
                transition_campaign,
                campaign_id,
                body.target_status,
                scope,
                expected_version=body.expected_version,
                actor_id=_admin_actor(request),
            )
        except CampaignConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_version_conflict", "message": "活動已被其他人更新，請重新載入。"},
            ) from exc
        except CampaignStateError as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "campaign_transition_not_allowed", "message": "目前狀態不能執行此操作。"},
            ) from exc
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail={"code": "campaign_not_found", "message": "找不到活動。"}
            ) from exc
        await _publish_campaign_change(row)
        return ApiResponse(data=_campaign_dto(row), meta=_meta(request))

    @router.get(
        "/promotions",
        tags=["v1-promotions"],
        operation_id="v1_list_promotions",
        response_model=PaginatedResponse[PromotionSummaryDTO],
    )
    async def promotions(
        request: Request, page: Page = 1, page_size: PageSize = 25
    ) -> PaginatedResponse[PromotionSummaryDTO]:
        scope = _scope(request, "rag.read")
        records = await asyncio.to_thread(promotion_service.list_promotions, scope)
        mapped = [
            PromotionSummaryDTO(
                offer_id=str(row.get("offer_id") or ""),
                title=str(row.get("title") or ""),
                status=str(row.get("status") or (row.get("metadata") or {}).get("status") or "draft"),
                enabled=bool(row.get("enabled", True)),
            )
            for row in records
        ]
        data, pagination = _page(mapped, page, page_size)
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/recommendations",
        tags=["v1-recommendations"],
        operation_id="v1_list_recommendations",
        response_model=PaginatedResponse[RecommendationEventDTO],
    )
    async def recommendations(
        request: Request, page: Page = 1, page_size: PageSize = 25
    ) -> PaginatedResponse[RecommendationEventDTO]:
        scope = _scope(request, "recommendations.read")
        records = await asyncio.to_thread(list_recommendation_events, scope, limit=5000)
        mapped = [
            RecommendationEventDTO(
                event_id=str(row.get("event_id") or row.get("id") or ""),
                event_type=str(row.get("event_type") or ""),
                session_id=str(row.get("session_id") or ""),
                item_id=str(row.get("item_id") or ""),
                item_name=str(row.get("item_name") or ""),
                surface=str(row.get("surface") or ""),
                source=str(row.get("source") or ""),
                audience=str(row.get("audience") or ("member" if row.get("is_member") else "guest")),
                offer_ids=[str(value) for value in (row.get("offer_ids") or [])],
                reasons=[str(value) for value in (row.get("reasons") or [])],
                experiment_id=str(row.get("experiment_id") or (row.get("metadata") or {}).get("experiment_id") or ""),
                variant_id=str(row.get("variant_id") or (row.get("metadata") or {}).get("variant_id") or ""),
                strategy=str(row.get("strategy") or (row.get("metadata") or {}).get("strategy") or ""),
                timestamp=_optional_datetime(row.get("timestamp")),
            )
            for row in records
        ]
        data, pagination = _page(mapped, page, page_size)
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/audits",
        tags=["v1-audits"],
        operation_id="v1_list_audits",
        response_model=PaginatedResponse[AuditRecordDTO],
    )
    async def audits(request: Request, page: Page = 1, page_size: PageSize = 25) -> PaginatedResponse[AuditRecordDTO]:
        scope = _scope(request, "audit.read")
        records = await asyncio.to_thread(admin_audit_service.list_admin_audits, 5000, scope)
        mapped = [
            AuditRecordDTO(
                audit_id=str(row.get("audit_id") or ""),
                actor=str(row.get("actor") or ""),
                action=str(row.get("action") or ""),
                target_type=str(row.get("target_type") or ""),
                target_id=str(row.get("target_id") or ""),
                created_at=_optional_datetime(row.get("created_at")),
            )
            for row in records
        ]
        data, pagination = _page(mapped, page, page_size)
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

    @router.get(
        "/settings",
        tags=["v1-settings"],
        operation_id="v1_get_settings",
        response_model=ApiResponse[SettingsDTO],
    )
    async def settings(request: Request) -> ApiResponse[SettingsDTO]:
        scope = _scope(request, "settings.read")
        values = await asyncio.to_thread(commercial_settings_repository.get_settings_scoped, scope)
        return ApiResponse(data=SettingsDTO(values=values), meta=_meta(request))

    # ── Milestone 7A typed write contracts ─────────────────────────────

    @router.patch(
        "/settings",
        tags=["v1-settings"],
        operation_id="v1_patch_settings",
        response_model=ApiResponse[SettingsDTO],
    )
    async def patch_settings(request: Request, body: SettingsPatchRequest) -> ApiResponse[SettingsDTO]:
        scope = _scope(request, "settings.write")
        principal = authorize_admin_request(request, "settings.write")
        values = await asyncio.to_thread(
            commercial_settings_repository.save_settings_scoped,
            dict(body.values),
            scope,
            actor_id=getattr(principal, "user_id", None),
        )
        await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "settings.patch",
            target_type="settings",
            target_id=str(scope.store_id),
            request=request,
            metadata={"actor_id": str(getattr(principal, "user_id", ""))},
            scope=scope,
        )
        return ApiResponse(data=SettingsDTO(values=values), meta=_meta(request))

    @router.put(
        "/availability/{item_id}",
        tags=["v1-availability"],
        operation_id="v1_put_availability",
        response_model=ApiResponse[AvailabilityDTO],
    )
    async def put_availability(
        request: Request, item_id: str, body: AvailabilityPutRequest
    ) -> ApiResponse[AvailabilityDTO]:
        scope = _scope(request, "catalog.availability.write")
        current = await asyncio.to_thread(availability_repository.get_availability_scoped, scope)
        sold_out = set(str(x) for x in (current.get("sold_out_ids") or []))
        if body.available:
            sold_out.discard(item_id)
        else:
            sold_out.add(item_id)
        current["sold_out_ids"] = sorted(sold_out)
        if body.reason:
            reasons = dict(current.get("reasons") or {})
            reasons[item_id] = body.reason
            current["reasons"] = reasons
        await asyncio.to_thread(availability_repository.save_availability_scoped, current, scope)
        return ApiResponse(
            data=AvailabilityDTO(item_id=item_id, available=body.available, reason=body.reason),
            meta=_meta(request),
        )

    @router.post(
        "/promotions",
        tags=["v1-promotions"],
        operation_id="v1_create_promotion",
        response_model=ApiResponse[PromotionSummaryDTO],
    )
    async def create_promotion(request: Request, body: PromotionCreateRequest) -> ApiResponse[PromotionSummaryDTO]:
        scope = _scope(request, "rag.write")
        row, errors = await asyncio.to_thread(
            promotion_service.save_promotion,
            {
                "offer_id": body.offer_id,
                "title": body.title,
                "enabled": body.enabled,
                "metadata": dict(body.metadata or {}),
            },
            scope=scope,
        )
        if errors or not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail={"code": "validation_error", "errors": errors})
        return ApiResponse(
            data=PromotionSummaryDTO(
                offer_id=str(row.get("offer_id") or body.offer_id),
                title=str(row.get("title") or body.title),
                status=str(row.get("status") or (row.get("metadata") or {}).get("status") or "draft"),
                enabled=bool(row.get("enabled", body.enabled)),
            ),
            meta=_meta(request),
        )

    @router.get(
        "/rag/knowledge",
        tags=["v1-rag"],
        operation_id="v1_list_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def list_rag_knowledge(request: Request) -> ApiResponse[dict]:
        scope = _scope(request, "rag.read")
        data = await asyncio.to_thread(
            knowledge_publication_runtime.default_module().list_items,
            scope=scope,
        )
        return ApiResponse(data=data, meta=_meta(request))

    @router.post(
        "/rag/knowledge",
        tags=["v1-rag"],
        operation_id="v1_create_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def create_rag_knowledge(request: Request, body: RagKnowledgeUpsertRequest) -> ApiResponse[dict]:
        scope = _scope(request, "rag.write")
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().create_draft,
                scope=scope,
                category=body.category,
                content_type=body.content_type,
                title=body.title,
                content=body.content,
                actor=_admin_actor(request),
                override_near_duplicate=body.override_near_duplicate,
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        row = {**row, "autopublish": await _autopublish(request, scope, str(row.get("item_id") or ""))}
        return ApiResponse(data=row, meta=_meta(request))

    @router.put(
        "/rag/knowledge/{item_id}",
        tags=["v1-rag"],
        operation_id="v1_revise_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def revise_rag_knowledge(
        request: Request, item_id: str, body: RagKnowledgeUpsertRequest
    ) -> ApiResponse[dict]:
        scope = _scope(request, "rag.write")
        if body.expected_row_revision is None:
            raise HTTPException(status_code=422, detail={"code": "expected_row_revision_required"})
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().revise_draft,
                scope=scope,
                item_id=item_id,
                expected_row_revision=body.expected_row_revision,
                category=body.category,
                content_type=body.content_type,
                title=body.title,
                content=body.content,
                actor=_admin_actor(request),
                override_near_duplicate=body.override_near_duplicate,
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        row = {**row, "autopublish": await _autopublish(request, scope, item_id)}
        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/publish",
        tags=["v1-rag"],
        operation_id="v1_publish_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def publish_rag_knowledge(request: Request, body: RagKnowledgePublishRequest) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().request_publication,
                scope=scope,
                item_ids=body.item_ids,
                actor=_admin_actor(request),
                retry_failures_only=body.retry_failures_only,
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/publication-attempts/{attempt_id}/resume",
        tags=["v1-rag"],
        operation_id="v1_resume_rag_publication_attempt",
        response_model=ApiResponse[dict],
    )
    async def resume_rag_publication_attempt(
        request: Request,
        attempt_id: str,
    ) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().ensure_attempt_enqueued,
                scope=scope,
                attempt_id=attempt_id,
                actor=_admin_actor(request),
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/knowledge/{item_id}/retire",
        tags=["v1-rag"],
        operation_id="v1_retire_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def retire_rag_knowledge(
        request: Request, item_id: str, body: RagKnowledgeActionRequest
    ) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().retire,
                scope=scope,
                item_id=item_id,
                expected_row_revision=body.expected_row_revision,
                actor=_admin_actor(request),
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        return ApiResponse(data=row, meta=_meta(request))

    @router.delete(
        "/rag/knowledge/{item_id}",
        tags=["v1-rag"],
        operation_id="v1_delete_rag_knowledge",
        response_model=ApiResponse[dict],
    )
    async def delete_rag_knowledge(
        request: Request,
        item_id: str,
        expected_row_revision: Annotated[int, Query(ge=1)],
    ) -> ApiResponse[dict]:
        """徹底刪除一筆知識（先下架清索引，再移除紀錄）。稽核事件保留可追溯。"""

        scope = _scope(request, "rag.publish")
        try:
            row = await asyncio.to_thread(
                knowledge_publication_runtime.default_module().delete,
                scope=scope,
                item_id=item_id,
                expected_row_revision=expected_row_revision,
                actor=_admin_actor(request),
            )
        except PublicationError as exc:
            raise _publication_http_error(exc) from exc
        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/rag/retrieval/test", tags=["v1-rag"], operation_id="v1_test_rag_retrieval", response_model=ApiResponse[dict]
    )
    async def test_rag_knowledge(request: Request, body: RagKnowledgeTestRequest) -> ApiResponse[dict]:
        scope = _scope(request, "rag.read")
        try:
            result = await retrieval_check_runtime.default_module().execute(
                query=body.query,
                scope=scope,
                method=body.method,
                top_k=body.top_k,
                relevance_policy=body.relevance_policy,
            )
        except RetrievalCheckError as exc:
            raise _retrieval_check_http_error(exc) from exc
        return ApiResponse(data=result, meta=_meta(request))

    @router.post(
        "/rag/retrieval/checks/{check_id}/confirm",
        tags=["v1-rag"],
        operation_id="v1_confirm_rag_retrieval_check",
        response_model=ApiResponse[dict],
    )
    async def confirm_rag_retrieval_check(
        request: Request,
        check_id: str,
    ) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        try:
            result = await asyncio.to_thread(
                retrieval_check_runtime.default_module().confirm,
                scope=scope,
                check_id=check_id,
                actor=_admin_actor(request),
            )
        except RetrievalCheckError as exc:
            raise _retrieval_check_http_error(exc) from exc
        return ApiResponse(data=result, meta=_meta(request))

    @router.get(
        "/rag/retrieval/configurations",
        tags=["v1-rag"],
        operation_id="v1_list_rag_configurations",
        response_model=ApiResponse[dict],
    )
    async def list_rag_configurations(request: Request) -> ApiResponse[dict]:
        scope = _scope(request, "rag.read")
        return ApiResponse(data=rag_knowledge_service.list_configurations(scope), meta=_meta(request))

    @router.post(
        "/rag/retrieval/configurations",
        tags=["v1-rag"],
        operation_id="v1_publish_rag_configuration",
        response_model=ApiResponse[dict],
    )
    async def publish_rag_configuration(request: Request, body: RagRetrievalConfigurationRequest) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        try:
            row = rag_knowledge_service.publish_configuration(
                scope=scope,
                method=body.method,
                top_k=body.top_k,
                relevance_policy=body.relevance_policy,
                source_version=body.source_version,
                actor=_admin_actor(request),
            )
        except rag_knowledge_service.RagKnowledgeError as exc:
            raise _rag_http_error(exc) from exc
        return ApiResponse(data=row, meta=_meta(request))

    @router.delete(
        "/rag/retrieval/configurations/{version}",
        tags=["v1-rag"],
        operation_id="v1_delete_rag_configuration",
        response_model=ApiResponse[dict],
    )
    async def delete_rag_configuration(request: Request, version: int) -> ApiResponse[dict]:
        scope = _scope(request, "rag.publish")
        actor = _admin_actor(request)
        try:
            row = rag_knowledge_service.delete_configuration(
                scope=scope,
                version=version,
                actor=actor,
            )
        except rag_knowledge_service.RagKnowledgeError as exc:
            raise _rag_http_error(exc) from exc
        await asyncio.to_thread(
            admin_audit_service.record_admin_action,
            "rag.retrieval_configuration.delete",
            target_type="rag_retrieval_configuration",
            target_id=str(version),
            request=request,
            metadata={"actor_id": actor},
            scope=scope,
        )
        return ApiResponse(data=row, meta=_meta(request))

    @router.post(
        "/fleet/devices/{device_id}/commands",
        tags=["v1-fleet"],
        operation_id="v1_issue_fleet_command",
        response_model=ApiResponse[FleetCommandDTO],
    )
    async def issue_fleet_command(
        request: Request, device_id: UUID, body: FleetCommandRequest
    ) -> ApiResponse[FleetCommandDTO]:
        scope = _scope(request, "device_identity.manage")
        row = await asyncio.to_thread(
            fleet_management_service.issue_command,
            device_id=device_id,
            tenant_id=scope.tenant_id,
            command=body.command,
            actor="admin",
            expires_at=body.expires_at,
        )
        return ApiResponse(
            data=FleetCommandDTO(
                command_id=str(row.get("command_id") or row.get("id") or ""),
                device_id=device_id,
                command=str(row.get("command") or body.command),
                status=str(row.get("status") or "pending"),
            ),
            meta=_meta(request),
        )

    @router.post(
        "/orders/{order_id}/transition",
        tags=["v1-orders"],
        operation_id="v1_transition_order",
        response_model=ApiResponse[OrderSummaryDTO],
    )
    async def transition_order(
        request: Request, order_id: UUID, body: OrderTransitionRequest
    ) -> ApiResponse[OrderSummaryDTO]:
        scope = _scope(request, "operations.write")
        target = OrderStatus(str(body.target_status).strip().lower())
        row = await asyncio.to_thread(
            checkout_order_repository.transition_order_scoped,
            order_id,
            target,
            scope,
        )
        return ApiResponse(
            data=OrderSummaryDTO(
                order_id=UUID(str(row.get("order_id") or order_id)),
                status=str(row.get("status") or target.value),
                currency=str(row.get("currency") or "TWD"),
                total=int(row.get("total") or 0),
                created_at=_optional_datetime(row.get("created_at")) or datetime.now(timezone.utc),
                member_id=UUID(str(row["member_id"])) if row.get("member_id") else None,
            ),
            meta=_meta(request),
        )

    return router
