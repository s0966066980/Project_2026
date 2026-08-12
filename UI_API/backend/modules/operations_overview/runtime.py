"""Compose the overview from the capabilities that own each number.

None of these tables belong to this module, so it asks their owners rather than
querying them directly. That keeps the roadmap's data-authority rule intact and
means a change to how, say, a Voice Turn counts as complete lands in one place.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models.commercial_scope import CommercialScope
from modules.voice_turn import runtime as voice_turn_runtime
from repositories import checkout_order_repository, recommendation_event_repository
from services import analytics_pipeline_service

from .module import OperationsOverviewModule


class CapabilityOverviewStore:
    def count_completed_voice_turns(self, *, scope: CommercialScope, since: str) -> int:
        return voice_turn_runtime.default_module().count_completed_since(scope=scope, since=since)

    def count_recommendations_shown(
        self, *, scope: CommercialScope, since: str, excluded_sources: tuple[str, ...]
    ) -> int:
        return recommendation_event_repository.count_shown_scoped(scope, since=since, excluded_sources=excluded_sources)

    def count_campaign_cta_clicks(self, *, scope: CommercialScope, since: str) -> int:
        return analytics_pipeline_service.count_campaign_cta_clicks(scope, since=since)

    def sum_confirmed_order_amount(self, *, scope: CommercialScope, since: str) -> tuple[int, str]:
        return checkout_order_repository.sum_confirmed_amount_scoped(scope, since=since)


def default_module() -> OperationsOverviewModule:
    return OperationsOverviewModule(store=CapabilityOverviewStore())


def since_days_ago(days: int = 1) -> str:
    """The window the overview reports on, as an inclusive UTC lower bound."""

    bounded = max(1, min(int(days), 31))
    return (datetime.now(timezone.utc) - timedelta(days=bounded)).isoformat()
