"""Durable background job contracts for the reliable worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID

ALLOWED_JOB_TYPES = frozenset(
    {
        "outbox.order_confirmed",
        "outbox.order_completed",
        "outbox.order_cancelled",
        "rag.studio.index",
        "rag.studio.evaluate",
        "report.generate",
        "event.deliver",
        "ai.background",
        "data.export",
        "cleanup.retention",
    }
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "secret",
        "authorization",
        "api_key",
        "apikey",
        "database_url",
        "phone",
        "credit_card",
        "cvv",
    }
)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class JobValidationError(ValueError):
    """Raised when a job contract is unsafe or unsupported."""


@dataclass(frozen=True)
class JobHandlerResult:
    success: bool
    retryable: bool = False
    safe_error: str = ""
    result_ref: str = ""
    side_effect_id: str = ""


@dataclass(frozen=True)
class OutboxDeliveryResult:
    success: bool
    retryable: bool = False
    safe_error: str = ""
    delivery_id: str = ""
    provider: str = ""
    acknowledged_at: datetime | None = None


@dataclass
class BackgroundJob:
    job_id: UUID
    tenant_id: UUID
    store_id: UUID | None
    job_type: str
    payload_ref: dict[str, Any]
    status: JobStatus
    attempt_count: int
    max_attempts: int
    idempotency_key: str
    scheduled_at: datetime
    available_at: datetime
    visibility_timeout_seconds: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    locked_by: str | None = None
    locked_until: datetime | None = None
    safe_error: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class QueueMetrics:
    depth: int
    oldest_age_seconds: float
    dead_letter_count: int = 0
    pending_outbox: int = 0


def validate_job_type(job_type: str) -> str:
    normalized = str(job_type or "").strip()
    if normalized not in ALLOWED_JOB_TYPES:
        raise JobValidationError(f"Unsupported job type: {normalized}")
    return normalized


def validate_job_payload_ref(payload_ref: Mapping[str, Any] | None) -> dict[str, Any]:
    if payload_ref is None:
        return {}
    if not isinstance(payload_ref, Mapping):
        raise JobValidationError("payload_ref must be a mapping of references")
    sanitized: dict[str, Any] = {}
    for key, value in payload_ref.items():
        key_text = str(key)
        lowered = key_text.casefold()
        if lowered in FORBIDDEN_PAYLOAD_KEYS or any(part in lowered for part in FORBIDDEN_PAYLOAD_KEYS):
            raise JobValidationError(f"payload_ref must not contain secret or PII key: {key_text}")
        if isinstance(value, dict):
            raise JobValidationError("payload_ref values must be scalar object references or scalar lists")
        if isinstance(value, list):
            if len(value) > 500:
                raise JobValidationError("payload_ref lists must stay under 500 items")
            normalized_items: list[str | int | float | bool] = []
            for item in value:
                if isinstance(item, (dict, list)) or item is None:
                    raise JobValidationError("payload_ref lists must contain scalar object references")
                text = str(item)
                if len(text) > 500:
                    raise JobValidationError("payload_ref list values must stay under 500 characters")
                normalized_items.append(item if isinstance(item, (str, int, float, bool)) else text)
            sanitized[key_text] = normalized_items
            continue
        if value is None:
            continue
        text = str(value)
        if len(text) > 500:
            raise JobValidationError("payload_ref values must stay under 500 characters")
        sanitized[key_text] = value if isinstance(value, (str, int, float, bool)) else text
    return sanitized


def compute_backoff_seconds(attempt_count: int, *, base_seconds: int = 2, cap_seconds: int = 300) -> int:
    attempt = max(1, int(attempt_count))
    delay = base_seconds * (2 ** (attempt - 1))
    return int(min(cap_seconds, delay))
