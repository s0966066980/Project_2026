"""Typed, versioned Admin read contracts with legacy API compatibility."""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Annotated, Literal, TypeVar
from uuid import UUID, uuid5

from fastapi import APIRouter, Query, Request, Security
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from api.v1.contracts import (
    AdminPrincipalDTO,
    ApiErrorResponse,
    ApiMeta,
    ApiResponse,
    AuditRecordDTO,
    AvailabilityDTO,
    AvailabilityPutRequest,
    CommercialContextDTO,
    FleetCommandDTO,
    FleetCommandRequest,
    MemberSummaryDTO,
    OrderSummaryDTO,
    OrderTransitionRequest,
    PaginatedResponse,
    PaginationMeta,
    PromotionCreateRequest,
    PromotionSummaryDTO,
    RagDocumentActionRequest,
    RagDocumentCreateRequest,
    RagDocumentDTO,
    RagReviewDTO,
    RecommendationEventDTO,
    SettingsDTO,
    SettingsPatchRequest,
)
from models.commercial_scope import CommercialScope
from models.order import OrderStatus
from repositories import checkout_order_repository, commercial_settings_repository, recommendation_event_repository
from repositories import availability_repository
from services import (
    admin_audit_service,
    fleet_management_service,
    member_service,
    promotion_service,
    rag_governance_service,
    rag_review_service,
)
from services.commercial_context_service import scope_from_admin_principal
from utils.auth_utils import authorize_admin_request

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
    return scope


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
        records = await asyncio.to_thread(member_service.admin_list, scope)
        needle = q.strip().casefold()
        if needle:
            records = [
                row
                for row in records
                if needle
                in " ".join(str(row.get(key) or "").casefold() for key in ("member_id", "nickname", "phone_masked"))
            ]
        records.sort(
            key=lambda row: (row.get(sort_by) is not None, row.get(sort_by) or ""), reverse=sort_order == "desc"
        )
        mapped = [
            MemberSummaryDTO(
                member_id=_member_uuid(row.get("member_id") or row.get("id"), scope),
                phone_masked=str(row.get("phone_masked") or ""),
                nickname=str(row.get("nickname") or ""),
                visit_count=int(row.get("visit_count") or 0),
                total_spend=int(row.get("total_spend") or 0),
                created_at=_optional_datetime(row.get("created_at")),
            )
            for row in records
        ]
        data, pagination = _page(mapped, page, page_size)
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
        records = await asyncio.to_thread(
            recommendation_event_repository.get_recommendation_events_scoped, scope, "", 5000
        )
        mapped = [
            RecommendationEventDTO(
                event_id=str(row.get("event_id") or row.get("id") or ""),
                event_type=str(row.get("event_type") or ""),
                session_id=str(row.get("session_id") or ""),
                item_id=str(row.get("item_id") or ""),
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

    @router.get(
        "/rag/reviews",
        tags=["v1-rag-governance"],
        operation_id="v1_list_rag_reviews",
        response_model=PaginatedResponse[RagReviewDTO],
    )
    async def rag_reviews(
        request: Request, page: Page = 1, page_size: PageSize = 25
    ) -> PaginatedResponse[RagReviewDTO]:
        _scope(request, "rag.read")
        records = await asyncio.to_thread(rag_review_service.list_reviews)
        mapped = [
            RagReviewDTO(
                review_id=str(row.get("review_id") or ""),
                status=str(row.get("status") or ""),
                title=str(row.get("title") or ""),
                updated_at=_optional_datetime(row.get("updated_at")),
            )
            for row in records
        ]
        data, pagination = _page(mapped, page, page_size)
        return PaginatedResponse(data=data, pagination=pagination, meta=_meta(request))

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

    @router.post(
        "/rag/documents",
        tags=["v1-rag-governance"],
        operation_id="v1_create_rag_document",
        response_model=ApiResponse[RagDocumentDTO],
    )
    async def create_rag_document(
        request: Request, body: RagDocumentCreateRequest
    ) -> ApiResponse[RagDocumentDTO]:
        scope = _scope(request, "rag.write")
        asset = await asyncio.to_thread(
            rag_governance_service.create_draft,
            document_id=body.document_id,
            content=body.content,
            source=body.source,
            owner=str(scope.tenant_id),
            tenant_id=scope.tenant_id,
            store_id=scope.store_id,
            actor="admin",
        )
        return ApiResponse(
            data=RagDocumentDTO(
                document_id=asset.document_id,
                version=asset.version,
                status=asset.status.value,
                checksum=asset.checksum,
                content_ref=asset.content_ref,
            ),
            meta=_meta(request),
        )

    @router.post(
        "/rag/documents/{document_id}/review",
        tags=["v1-rag-governance"],
        operation_id="v1_review_rag_document",
        response_model=ApiResponse[RagDocumentDTO],
    )
    async def review_rag_document(
        request: Request, document_id: str, body: RagDocumentActionRequest
    ) -> ApiResponse[RagDocumentDTO]:
        _scope(request, "rag.review")
        asset = await asyncio.to_thread(
            rag_governance_service.submit_for_review,
            document_id,
            body.version,
            actor=body.actor,
        )
        return ApiResponse(
            data=RagDocumentDTO(
                document_id=asset.document_id,
                version=asset.version,
                status=asset.status.value,
                checksum=asset.checksum,
                content_ref=asset.content_ref,
            ),
            meta=_meta(request),
        )

    @router.post(
        "/rag/documents/{document_id}/publish",
        tags=["v1-rag-governance"],
        operation_id="v1_publish_rag_document",
        response_model=ApiResponse[RagDocumentDTO],
    )
    async def publish_rag_document(
        request: Request, document_id: str, body: RagDocumentActionRequest
    ) -> ApiResponse[RagDocumentDTO]:
        _scope(request, "rag.publish")
        asset = await asyncio.to_thread(
            rag_governance_service.publish,
            document_id,
            body.version,
            actor=body.actor,
        )
        return ApiResponse(
            data=RagDocumentDTO(
                document_id=asset.document_id,
                version=asset.version,
                status=asset.status.value,
                checksum=asset.checksum,
                content_ref=asset.content_ref,
            ),
            meta=_meta(request),
        )

    @router.post(
        "/rag/documents/{document_id}/rollback",
        tags=["v1-rag-governance"],
        operation_id="v1_rollback_rag_document",
        response_model=ApiResponse[RagDocumentDTO],
    )
    async def rollback_rag_document(
        request: Request, document_id: str, body: RagDocumentActionRequest
    ) -> ApiResponse[RagDocumentDTO]:
        _scope(request, "rag.rollback")
        asset = await asyncio.to_thread(
            rag_governance_service.rollback,
            document_id,
            body.version,
            actor=body.actor,
        )
        return ApiResponse(
            data=RagDocumentDTO(
                document_id=asset.document_id,
                version=asset.version,
                status=asset.status.value,
                checksum=asset.checksum,
                content_ref=asset.content_ref,
            ),
            meta=_meta(request),
        )

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
