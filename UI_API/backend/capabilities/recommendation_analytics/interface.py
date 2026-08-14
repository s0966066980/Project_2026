"""Published Recommendation and Analytics application surface."""

from capabilities.recommendation_analytics.contracts import EffectivenessReport, TouchReceipt
from modules.analytics import (
    TouchValidationError,
    build_effectiveness_report,
    build_order_attributions,
    record_touch,
)

# These used to be call-time proxies into services/ and repositories/, which is
# what kept this capability on the frozen legacy-layer list. The recommendation
# and analytics implementations now live in their own modules.
from modules.analytics import _pipeline as analytics_pipeline_service
from modules.recommendation import _ai_push_service as ai_push_service
from modules.recommendation import _event_service as recommendation_event_service
from modules.recommendation import _interaction_event as interaction_event_service
from modules.recommendation import _intervention_pipeline as intervention_pipeline_service
from modules.recommendation import _scenario as scenario_service
from modules.recommendation import decide, list_events
from modules.recommendation.adapters import events as recommendation_event_repository
from modules.recommendation.adapters import interactions as interaction_event_repository


class _OperationsStatsProxy:
    """Session statistics belong to Operations; this capability only reads them."""

    def __getattr__(self, name: str):
        from capabilities.operations_configuration import interface as operations

        return getattr(operations, name)


stats_service = _OperationsStatsProxy()

__all__ = [
    "EffectivenessReport",
    "TouchReceipt",
    "TouchValidationError",
    "build_effectiveness_report",
    "decide",
    "list_events",
    "build_order_attributions",
    "record_touch",
    "analytics_pipeline_service",
    "ai_push_service",
    "recommendation_event_repository",
    "recommendation_event_service",
    "interaction_event_repository",
    "interaction_event_service",
    "intervention_pipeline_service",
    "scenario_service",
    "stats_service",
]
