"""The four numbers Batch P1 shows a store manager, and what each one means.

Every count here is deliberately narrow. A store manager reads these to decide
whether the kiosk is doing its job, so a number that quietly includes something
the server never authorised — or that the customer never actually received — is
worse than no number at all.

The definitions travel with the values rather than living only in a document,
because the screen has to state them and a report built on these records must
not be free to reinterpret them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from models.commercial_scope import CommercialScope

# Sources the kiosk assigns to an item it picked itself when the recommendation API
# gave it nothing usable. The events are kept so later conversions have a source
# record, and excluded here so they are never read as recommendation performance
# (ADR-0054).
PLACEHOLDER_RECOMMENDATION_SOURCES: tuple[str, ...] = ("local_default", "local_fallback")

VOICE_SUCCESS_CAVEAT = "語音已產生並送出的次數，不是顧客實際聽到的次數"
RECOMMENDATION_CAVEAT = "不含 kiosk 在推薦服務失效時自行挑選的佔位品項"
CONFIRMED_AMOUNT_CAVEAT = "已確認訂單的金額，不含未完成結帳的購物車"
CAMPAIGN_CTA_CAVEAT = "顧客實際點擊活動入口的次數"


@dataclass(frozen=True)
class OperationsOverview:
    voice_turns_completed: int
    recommendations_shown: int
    campaign_cta_clicks: int
    confirmed_order_amount: int
    currency: str

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "definitions": {
                "voice_turns_completed": VOICE_SUCCESS_CAVEAT,
                "recommendations_shown": RECOMMENDATION_CAVEAT,
                "campaign_cta_clicks": CAMPAIGN_CTA_CAVEAT,
                "confirmed_order_amount": CONFIRMED_AMOUNT_CAVEAT,
            },
        }


class OverviewStore(Protocol):
    def count_completed_voice_turns(self, *, scope: CommercialScope, since: str) -> int: ...

    def count_recommendations_shown(
        self, *, scope: CommercialScope, since: str, excluded_sources: tuple[str, ...]
    ) -> int: ...

    def count_campaign_cta_clicks(self, *, scope: CommercialScope, since: str) -> int: ...

    def sum_confirmed_order_amount(self, *, scope: CommercialScope, since: str) -> tuple[int, str]: ...


class OperationsOverviewModule:
    def __init__(self, *, store: OverviewStore):
        self._store = store

    def build(self, *, scope: CommercialScope, since: str) -> OperationsOverview:
        amount, currency = self._store.sum_confirmed_order_amount(scope=scope, since=since)
        return OperationsOverview(
            voice_turns_completed=self._store.count_completed_voice_turns(scope=scope, since=since),
            # The exclusion is applied by the store rather than filtered afterwards so a
            # placeholder can never be counted and then subtracted back out.
            recommendations_shown=self._store.count_recommendations_shown(
                scope=scope,
                since=since,
                excluded_sources=PLACEHOLDER_RECOMMENDATION_SOURCES,
            ),
            campaign_cta_clicks=self._store.count_campaign_cta_clicks(scope=scope, since=since),
            confirmed_order_amount=amount,
            currency=currency,
        )


PUSH_FUNNEL_CAVEAT = "以曝光為分母：被顧客看見的推薦裡，有多少最後成為已確認訂單"
PUSH_SESSION_CAVEAT = "每筆為一張已確認訂單，不是每一次點餐嘗試"


@dataclass(frozen=True)
class PushFunnel:
    """Did the recommendation work, counted from what actually happened.

    Every stage is a distinct durable fact rather than a derived guess:
    impressions and add-to-carts are commercial touches the Kiosk reported,
    orders are rows in the confirmed-order store, and an attributed order is
    one the analytics capability could tie back to a specific impression.

    This replaces a session-log projection whose only writer had no callers, so
    the numbers it produced were structurally zero. The definitions live here
    because the screen has to state them.
    """

    impressions: int
    add_to_carts: int
    orders: int
    attributed_orders: int

    # There is no `cumulative_score`. The old one was a running total kept in
    # the session log, and the session log had no writer; inventing a score
    # from funnel counts would put a number on the screen that means nothing.

    @property
    def success_rate(self) -> float:
        return round(self.attributed_orders / self.impressions, 4) if self.impressions else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_sessions": self.orders,
            "total_ai_push_cart_clicks": self.add_to_carts,
            "success_sessions": self.attributed_orders,
            "failure_sessions": max(0, self.impressions - self.attributed_orders),
            "success_rate": self.success_rate,
            "impressions": self.impressions,
            "definitions": {
                "success_rate": PUSH_FUNNEL_CAVEAT,
                "sessions": PUSH_SESSION_CAVEAT,
            },
        }


class PushFunnelStore(Protocol):
    def count_touches(self, *, scope: CommercialScope, since: str, event_type: str) -> int: ...

    def count_confirmed_orders(self, *, scope: CommercialScope, since: str) -> int: ...

    def count_attributed_orders(self, *, scope: CommercialScope, since: str) -> int: ...

    def recent_confirmed_orders(self, *, scope: CommercialScope, limit: int) -> list[dict[str, Any]]: ...


class PushFunnelModule:
    """The operations overview's push half, composed from its owners."""

    def __init__(self, *, store: PushFunnelStore) -> None:
        self._store = store

    def funnel(self, *, scope: CommercialScope, since: str) -> PushFunnel:
        return PushFunnel(
            impressions=self._store.count_touches(scope=scope, since=since, event_type="impression"),
            add_to_carts=self._store.count_touches(scope=scope, since=since, event_type="add_to_cart"),
            orders=self._store.count_confirmed_orders(scope=scope, since=since),
            attributed_orders=self._store.count_attributed_orders(scope=scope, since=since),
        )

    def sessions(self, *, scope: CommercialScope, limit: int = 200) -> list[dict[str, Any]]:
        """One row per confirmed order, which is what the detail table means.

        The old table listed session-log entries; there were none, so it was
        always empty. A confirmed order is the durable fact closest to what an
        operator is looking for when they open 點餐記錄明細.
        """

        return self._store.recent_confirmed_orders(scope=scope, limit=limit)
