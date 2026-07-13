"""Promotion / recommendation strategy governance contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID


class StrategyStatus(str, Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    PAUSED = "paused"
    RETIRED = "retired"


@dataclass
class StrategyVersion:
    strategy_id: str
    version: int
    status: StrategyStatus
    scope_tenant_id: UUID | None
    scope_store_id: UUID | None
    eligibility: dict[str, Any]
    ranking_config: dict[str, Any]
    effective_from: str
    effective_to: str
    created_at: str = ""
    reviewed_at: str = ""
    published_at: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ExperimentAssignment:
    experiment_id: str
    variant: str
    assignment_key: str
    deterministic: bool = True


@dataclass(frozen=True)
class RecommendationEventRecord:
    event_id: str
    strategy_version: str
    experiment_id: str
    variant: str
    tenant_id: UUID | None
    store_id: UUID | None
    session_ref: str
    member_ref: str
    surface: str
    rank: int
    score: float
    reason_code: str
    timestamp: str
    event_type: str
