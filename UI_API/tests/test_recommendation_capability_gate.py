"""Recommendation's gate: an enhancement may never become a blocker.

The Module Independence Gate for Recommendation asks for provider failure, an
empty recommendation, invalid and unavailable products filtered, a
recommendation that cannot override price, and a recommendation timeout that
does not block the Kiosk.

Recommendation is declared an enhancement in `CONTEXT.md`, not a transaction
authority. Every check here is a way of asking the same question: when this
capability has a bad day, does the customer still get a menu and a price?
"""

import ast
import pathlib
import uuid

import pytest

from models.commercial_scope import CommercialScope
from modules.recommendation import application as recommendation
from modules.recommendation import decide

pytestmark = [pytest.mark.unit, pytest.mark.contract]

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")

MENU = [
    {"id": "item_a", "name": "Burger", "price": 120},
    {"id": "item_b", "name": "Fries", "price": 60},
]


def _context(**overrides) -> dict:
    context = {"menu_items": [dict(item) for item in MENU], "controls": {}}
    context.update(overrides)
    return context


def _decide(**kwargs):
    """Decide without a scope, so nothing is written to the analytics store."""

    return decide(_context(**kwargs.pop("context", {})), session_id=f"rec-{uuid.uuid4().hex[:8]}", **kwargs)


@pytest.fixture
def engine(monkeypatch):
    """Control what the recommendation engine does on this call."""

    class _Engine:
        outcome: object = {"items": [{"id": "item_a", "score": 9}], "strategy": "weighted_random"}

        def recommend(self, context, limit, randomize, strategy, experiment):
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    installed = _Engine()
    monkeypatch.setattr(recommendation, "recommendation_engine_service", installed)
    return installed


# --- the engine has a bad day ----------------------------------------------


def test_a_provider_failure_still_returns_something_to_show(engine):
    engine.outcome = RuntimeError("the model host is down")

    decision = _decide(limit=2)

    assert decision["items"], "the Kiosk was handed nothing to display"
    assert decision["fallback_status"] == "engine_fallback"


def test_a_provider_timeout_does_not_block_the_kiosk(engine):
    engine.outcome = TimeoutError("inference timed out")

    decision = _decide(limit=1)

    assert [item["id"] for item in decision["items"]] == ["item_a"]
    assert decision["items"][0]["reasons"] == ["deterministic_fallback"]


def test_an_empty_recommendation_falls_back_rather_than_showing_a_blank(engine):
    engine.outcome = {"items": [], "strategy": "weighted_random"}

    decision = _decide(limit=2)

    assert len(decision["items"]) == 2
    assert decision["fallback_status"] == "engine_fallback"


def test_the_fallback_is_marked_as_a_fallback(engine):
    """An operator reading the decision must be able to tell it was degraded."""

    engine.outcome = RuntimeError("down")
    degraded = _decide()

    engine.outcome = {"items": [{"id": "item_a", "score": 9}], "strategy": "weighted_random"}
    healthy = _decide()

    assert degraded["fallback_status"] == "engine_fallback"
    assert healthy["fallback_status"] == "not_used"


def test_an_engine_failure_with_nothing_to_fall_back_to_is_still_an_answer(engine):
    """No menu and no engine: an empty list, not an exception."""

    engine.outcome = RuntimeError("down")

    decision = decide({"menu_items": [], "controls": {}}, session_id="rec-empty", limit=2)

    assert decision["items"] == []
    assert decision["decision_id"]


# --- what may be recommended ------------------------------------------------


def test_an_item_the_caller_excluded_is_never_recommended(engine):
    """Exclusions are how sold-out and unavailable items are kept off the surface."""

    engine.outcome = RuntimeError("down")

    decision = _decide(context={"controls": {"exclude_item_ids": ["item_a"]}}, limit=2)

    assert [item["id"] for item in decision["items"]] == ["item_b"]


def test_an_item_with_no_id_is_not_recommended(engine):
    """An item nobody can order is not a recommendation."""

    engine.outcome = RuntimeError("down")

    decision = decide(
        {"menu_items": [{"name": "Ghost", "price": 100}, {"id": "item_b", "name": "Fries"}], "controls": {}},
        session_id="rec-invalid",
        limit=2,
    )

    assert [item["id"] for item in decision["items"]] == ["item_b"]


def test_no_more_items_come_back_than_were_asked_for(engine):
    engine.outcome = {"items": [{"id": "item_a"}, {"id": "item_b"}], "strategy": "weighted_random"}

    decision = _decide(limit=1)

    assert len(decision["items"]) == 1
    assert decision["items"][0]["rank"] == 1


def test_every_recommended_item_carries_the_decision_that_produced_it(engine):
    """Without the decision id, no touch can be attributed to anything."""

    engine.outcome = {"items": [{"id": "item_a"}, {"id": "item_b"}], "strategy": "weighted_random"}

    decision = _decide(limit=2)

    assert {item["decision_id"] for item in decision["items"]} == {decision["decision_id"]}
    assert [item["rank"] for item in decision["items"]] == [1, 2]


def test_an_offer_is_recommended_by_reference_and_version(engine):
    """A recommendation points at an offer; it does not restate its terms."""

    engine.outcome = {
        "items": [{"id": "item_a", "offers": [{"offer_id": "cmp_1", "version": 4, "promo_price": 1}]}],
        "strategy": "weighted_random",
    }

    decision = _decide(limit=1)

    assert decision["items"][0]["offer_versions"] == [{"offer_id": "cmp_1", "version": 4}]


# --- the prohibition: not a transaction authority ---------------------------

BACKEND = pathlib.Path(__file__).resolve().parents[1] / "backend"
TRANSACTION_TREES = (
    BACKEND / "modules" / "cart",
    BACKEND / "modules" / "checkout_confirmation",
    BACKEND / "modules" / "ordering_entry",
    BACKEND / "modules" / "promotion",
)
RECOMMENDATION_ROOTS = {
    "capabilities.recommendation_analytics",
    "modules.recommendation",
    "modules.analytics",
}


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def test_the_transaction_path_never_reads_a_recommendation():
    """Price and order come from the catalog and the campaign, never from a suggestion.

    Checked as an import rule because that is the only way to state it once and
    have it hold for every future caller: if cart, checkout, ordering entry and
    promotion cannot reach recommendation, no recommendation can move a price.
    """

    offenders: list[str] = []
    for tree in TRANSACTION_TREES:
        for source in tree.rglob("*.py"):
            for imported in _imported_modules(source):
                if any(imported == root or imported.startswith(f"{root}.") for root in RECOMMENDATION_ROOTS):
                    offenders.append(f"{source.relative_to(BACKEND)} imports {imported}")

    assert offenders == [], "the transaction path read a recommendation: " + "; ".join(offenders)


def test_the_prohibition_names_trees_that_exist():
    """A rule pointed at a directory nobody has would pass forever."""

    missing = [str(tree) for tree in TRANSACTION_TREES if not tree.is_dir()]
    missing += [root for root in RECOMMENDATION_ROOTS if not (BACKEND / pathlib.Path(*root.split("."))).is_dir()]

    assert missing == [], f"the prohibition names trees that do not exist: {missing}"


# --- analytics is downstream, not a dependency ------------------------------


def test_an_analytics_outage_does_not_take_recommendations_down(engine):
    """Recording that a decision happened must not decide whether it may happen.

    Analytics is downstream of the decision. If the sink being unavailable can
    stop the Kiosk from showing a recommendation, an Optional capability is
    gating an enhancement that is meant to degrade quietly.
    """

    from modules.operations import _observability as observability

    class _BrokenSink:
        def write(self, envelope):
            raise RuntimeError("analytics store is unavailable")

    engine.outcome = {"items": [{"id": "item_a"}], "strategy": "weighted_random"}
    before = (
        observability.metrics_snapshot().get("recommendation_touch_record_degraded_total", {}).get("unavailable", 0)
    )

    decision = decide(
        _context(),
        session_id="rec-analytics",
        scope=CommercialScope(TENANT, STORE),
        limit=1,
        sink=_BrokenSink(),
    )

    after = observability.metrics_snapshot().get("recommendation_touch_record_degraded_total", {}).get("unavailable", 0)

    assert decision["items"], "a broken analytics sink stopped the recommendation"
    assert after == before + 1, "the lost touch was never counted, so the attribution gap is invisible"
