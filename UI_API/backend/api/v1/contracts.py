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


class RagDocumentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(default="", max_length=120)
    content: str = Field(min_length=1, max_length=200_000)
    source: str = Field(default="api", max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=200)


class RagDocumentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    actor: str = Field(default="admin", max_length=100)


class RagDocumentDTO(BaseModel):
    document_id: str
    version: int
    status: str
    checksum: str
    content_ref: str = ""


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
