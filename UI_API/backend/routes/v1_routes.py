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
    CommercialContextDTO,
    MemberSummaryDTO,
    OrderSummaryDTO,
    PaginatedResponse,
    PaginationMeta,
    PromotionSummaryDTO,
    RagReviewDTO,
    RecommendationEventDTO,
    SettingsDTO,
)
from models.commercial_scope import CommercialScope
from repositories import checkout_order_repository, commercial_settings_repository, recommendation_event_repository
from services import admin_audit_service, member_service, promotion_service, rag_review_service
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

    return router
