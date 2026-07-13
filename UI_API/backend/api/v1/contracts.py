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


class RecommendationEventDTO(BaseModel):
    event_id: str
    event_type: str
    session_id: str
    item_id: str
    timestamp: datetime | None = None


class AuditRecordDTO(BaseModel):
    audit_id: str
    actor: str
    action: str
    target_type: str
    target_id: str
    created_at: datetime | None = None


class RagReviewDTO(BaseModel):
    review_id: str
    status: str
    title: str
    updated_at: datetime | None = None


class SettingsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, JsonValue]
