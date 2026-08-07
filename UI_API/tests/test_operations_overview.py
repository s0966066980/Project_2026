"""What each number on the operations overview counts, and what it leaves out.

Every one of the four excludes something a reader would otherwise assume was
included, which is exactly how a reporting number stops meaning what its label
says. These pin the exclusions and the definitions that must reach the screen.
"""

from modules.operations_overview.module import (
    PLACEHOLDER_RECOMMENDATION_SOURCES,
    OperationsOverviewModule,
)

from models.commercial_scope import LEGACY_DEFAULT_SCOPE

SCOPE = LEGACY_DEFAULT_SCOPE
SINCE = "2026-08-06T00:00:00+00:00"


class _Store:
    def __init__(self, *, voice=0, recommendations=0, campaign=0, amount=0, currency="TWD"):
        self._voice = voice
        self._recommendations = recommendations
        self._campaign = campaign
        self._amount = amount
        self._currency = currency
        self.recommendation_exclusions: tuple[str, ...] = ()
        self.windows: list[str] = []

    def count_completed_voice_turns(self, *, scope, since):
        self.windows.append(since)
        return self._voice

    def count_recommendations_shown(self, *, scope, since, excluded_sources):
        self.recommendation_exclusions = excluded_sources
        return self._recommendations

    def count_campaign_cta_clicks(self, *, scope, since):
        return self._campaign

    def sum_confirmed_order_amount(self, *, scope, since):
        return self._amount, self._currency


def _build(**kwargs):
    store = _Store(**kwargs)
    return store, OperationsOverviewModule(store=store).build(scope=SCOPE, since=SINCE)


def test_the_four_counts_are_reported_together():
    _, overview = _build(voice=12, recommendations=48, campaign=7, amount=3250)

    assert overview.voice_turns_completed == 12
    assert overview.recommendations_shown == 48
    assert overview.campaign_cta_clicks == 7
    assert overview.confirmed_order_amount == 3250
    assert overview.currency == "TWD"


# The kiosk picks a placeholder item when the recommendation service is unreachable.
# Counting it would report an activity nothing on the server chose.
def test_placeholder_recommendation_sources_are_excluded_at_the_source():
    store, _ = _build()

    assert store.recommendation_exclusions == PLACEHOLDER_RECOMMENDATION_SOURCES
    assert "local_default" in store.recommendation_exclusions
    assert "local_fallback" in store.recommendation_exclusions


def test_an_empty_store_reports_zeros_rather_than_nothing():
    _, overview = _build()

    assert overview.voice_turns_completed == 0
    assert overview.confirmed_order_amount == 0
    assert overview.currency == "TWD"


class TestDefinitionsReachTheScreen:
    """A number whose caveat lives only in a document will be read without it."""

    def test_every_count_carries_its_definition(self):
        _, overview = _build(voice=1, recommendations=1, campaign=1, amount=1)
        definitions = overview.as_dict()["definitions"]

        assert set(definitions) == {
            "voice_turns_completed",
            "recommendations_shown",
            "campaign_cta_clicks",
            "confirmed_order_amount",
        }
        assert all(text.strip() for text in definitions.values())

    def test_voice_success_says_it_is_not_what_the_customer_heard(self):
        _, overview = _build()

        assert "不是顧客實際聽到" in overview.as_dict()["definitions"]["voice_turns_completed"]

    def test_recommendations_say_placeholders_are_excluded(self):
        _, overview = _build()

        assert "佔位" in overview.as_dict()["definitions"]["recommendations_shown"]

    def test_the_amount_says_it_is_confirmed_orders_only(self):
        _, overview = _build()

        assert "已確認" in overview.as_dict()["definitions"]["confirmed_order_amount"]


def test_the_reporting_window_is_applied_to_every_source():
    store, _ = _build()

    assert store.windows == [SINCE]
