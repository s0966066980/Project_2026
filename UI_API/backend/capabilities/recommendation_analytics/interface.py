"""Published Recommendation and Analytics application surface."""

from capabilities.recommendation_analytics.contracts import EffectivenessReport, TouchReceipt
from modules.analytics import TouchValidationError, build_effectiveness_report, record_touch
from modules.recommendation import decide, list_events


class _AnalyticsPipelineServiceProxy:
    def __getattr__(self, name: str):
        from services import analytics_pipeline_service

        return getattr(analytics_pipeline_service, name)


analytics_pipeline_service = _AnalyticsPipelineServiceProxy()


class _AiPushServiceProxy:
    """Expose kiosk recommendation composition through this capability."""

    def __getattr__(self, name: str):
        from services import ai_push_service

        return getattr(ai_push_service, name)


ai_push_service = _AiPushServiceProxy()


class _LegacyAnalyticsProxy:
    def __init__(self, module_name: str):
        self._module_name = module_name

    def __getattr__(self, name: str):
        import importlib

        return getattr(importlib.import_module(self._module_name), name)


recommendation_event_repository = _LegacyAnalyticsProxy("repositories.recommendation_event_repository")
recommendation_event_service = _LegacyAnalyticsProxy("services.recommendation_event_service")
interaction_event_repository = _LegacyAnalyticsProxy("repositories.interaction_event_repository")
interaction_event_service = _LegacyAnalyticsProxy("services.interaction_event_service")
intervention_pipeline_service = _LegacyAnalyticsProxy("services.intervention_pipeline_service")
scenario_service = _LegacyAnalyticsProxy("services.scenario_service")
stats_service = _LegacyAnalyticsProxy("services.stats_service")

__all__ = [
    "EffectivenessReport",
    "TouchReceipt",
    "TouchValidationError",
    "build_effectiveness_report",
    "decide",
    "list_events",
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
