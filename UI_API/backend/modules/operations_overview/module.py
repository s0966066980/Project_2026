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
