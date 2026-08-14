"""Compose the overview from the capabilities that own each number.

None of these tables belong to this module, so it asks their owners rather than
querying them directly. That keeps the roadmap's data-authority rule intact and
means a change to how, say, a Voice Turn counts as complete lands in one place.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from models.commercial_scope import CommercialScope
from modules.analytics import _pipeline as analytics_pipeline_service
from modules.analytics import build_effectiveness_report
from modules.checkout_confirmation.adapters import orders as checkout_order_repository
from modules.recommendation.adapters import events as recommendation_event_repository
from modules.voice_turn import runtime as voice_turn_runtime

from .module import OperationsOverviewModule, PushFunnelModule


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


class CapabilityPushFunnelStore:
    """The push funnel, asked of the capabilities that own each fact.

    Same rule as the overview above: none of these tables belong here. The
    counts come from the analytics touch log, the confirmed-order store and
    the attribution table, each through its owner's published reader.
    """

    def _report(self, *, scope: CommercialScope, since: str):
        events = analytics_pipeline_service.list_events(tenant_id=scope.tenant_id, store_id=scope.store_id, since=since)
        attributions = checkout_order_repository.list_order_touch_attributions_scoped(scope, since=since)
        return build_effectiveness_report(events, attributions)

    def count_touches(self, *, scope: CommercialScope, since: str, event_type: str) -> int:
        """Count one funnel stage, asking the reader that owns what a stage is.

        Counting the log directly returns zero for every stage: the envelope
        type is namespaced (`commercial_touch.impression`) and the payload does
        not carry the stage at all. Deduplication by impression id is part of
        the definition too, and lives in the same place.
        """

        report = self._report(scope=scope, since=since)
        return int({"impression": report.impressions, "add_to_cart": report.add_to_carts}.get(event_type, 0))

    def count_confirmed_orders(self, *, scope: CommercialScope, since: str) -> int:
        return len(checkout_order_repository.list_confirmed_orders_scoped(scope, limit=500))

    def count_attributed_orders(self, *, scope: CommercialScope, since: str) -> int:
        rows = checkout_order_repository.list_order_touch_attributions_scoped(scope, since=since)
        # One order can carry several attributed lines; the funnel counts orders.
        return len({str(row.get("order_id") or "") for row in rows if row.get("order_id")})

    def recent_confirmed_orders(self, *, scope: CommercialScope, limit: int) -> list[dict]:
        return checkout_order_repository.list_confirmed_orders_scoped(scope, limit=limit)


def default_module() -> OperationsOverviewModule:
    return OperationsOverviewModule(store=CapabilityOverviewStore())


def default_push_funnel_module() -> PushFunnelModule:
    return PushFunnelModule(store=CapabilityPushFunnelStore())


def since_days_ago(days: int = 1) -> str:
    """The window the overview reports on, as an inclusive UTC lower bound."""

    bounded = max(1, min(int(days), 31))
    return (datetime.now(timezone.utc) - timedelta(days=bounded)).isoformat()
