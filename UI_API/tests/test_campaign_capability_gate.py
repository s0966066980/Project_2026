"""Campaign's gate: one lifecycle, one price authority, one active projection.

The Module Independence Gate for Campaign & Promotion asks for allowed and
forbidden state transitions, content edits that do not move the lifecycle,
publication atomicity, schedule timezone and bounds, server-authoritative
promotion pricing, push copy resolution, refusal of unverified promotion
claims, concurrent edit version conflicts, and a Kiosk that reads only the
active projection.

The lifecycle and pricing rules are pure, so they are checked directly. The
campaign store is exercised through the real repository where the question is
about persistence — a fake cannot answer "did two editors both win".
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.commercial_scope import CommercialScope
from modules.promotion import contracts
from modules.promotion.application import (
    CAMPAIGN_EDITABLE_STATUSES,
    CAMPAIGN_TRANSITIONS,
    evaluate_promotion,
    project_item_price,
    quote_promotion,
    select_promotion_quote,
)
from modules.promotion.contracts import PromotionContext
from repositories import postgres_utils
from services.push_copy_service import (
    STATUS_BASE,
    STATUS_CAMPAIGN,
    STATUS_DESCRIPTION,
    active_offer_ids,
    resolve_copy,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]

TENANT = uuid.UUID("00000000-0000-4000-8000-000000000001")
STORE = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _context(**overrides) -> PromotionContext:
    values = {
        "now": datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        "scope": CommercialScope(TENANT, STORE),
    }
    values.update(overrides)
    return PromotionContext(**values)


def _promotion(**overrides) -> dict:
    """An offer as the pricing authority reads one.

    `promo_price` is the promoted price itself, not a discount to subtract:
    `quote_promotion` never reads `discount_type`/`discount_value`, which are
    campaign-authoring fields. An offer that carries only those two prices
    nothing — checked below, because it is an easy way to publish a campaign
    that appears live and changes no price.
    """

    promotion = {
        "id": "cmp_gate",
        "title": "Gate promotion",
        "status": "active",
        "promo_price": 80,
        "tenant_id": str(TENANT),
        "store_id": str(STORE),
    }
    promotion.update(overrides)
    return promotion


# --- lifecycle -------------------------------------------------------------


def test_archived_is_the_end_of_the_line():
    """Nothing may bring an archived campaign back; that is what archived means."""

    assert CAMPAIGN_TRANSITIONS["archived"] == set()


def test_a_campaign_cannot_jump_from_draft_to_active():
    """Review exists so nobody publishes a price by accident."""

    assert "active" not in CAMPAIGN_TRANSITIONS["draft"]
    assert "review" in CAMPAIGN_TRANSITIONS["draft"]


def test_every_transition_target_is_itself_a_known_state():
    states = set(CAMPAIGN_TRANSITIONS)
    for source, targets in CAMPAIGN_TRANSITIONS.items():
        unknown = targets - states
        assert unknown == set(), f"{source} can move to states that do not exist: {unknown}"


def test_a_live_campaign_is_not_editable_without_pausing_it_first():
    """Editing the terms of a running offer changes what customers are being sold."""

    assert "active" not in CAMPAIGN_EDITABLE_STATUSES
    assert "scheduled" not in CAMPAIGN_EDITABLE_STATUSES
    assert {"paused", "ended"} <= CAMPAIGN_EDITABLE_STATUSES


# --- pricing authority -----------------------------------------------------


def test_a_promotion_for_another_store_does_not_apply_here():
    result = evaluate_promotion(_promotion(store_id=str(uuid.uuid4())), _context())

    assert result.eligible is False


def test_an_inactive_promotion_does_not_price():
    result = evaluate_promotion(_promotion(status="paused"), _context())

    assert result.eligible is False


def test_a_promotion_outside_its_window_does_not_price():
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    future = (now + timedelta(days=2)).isoformat()
    later = (now + timedelta(days=3)).isoformat()

    result = evaluate_promotion(_promotion(starts_at=future, ends_at=later), _context(now=now))

    assert result.eligible is False


@pytest.mark.parametrize("promoted", [0, -50])
def test_an_offer_can_never_price_an_item_at_or_below_zero(promoted):
    quote = quote_promotion(_promotion(promo_price=promoted), _context(), base_price=100)

    assert quote.eligible is False, "an offer priced the item at or below nothing"
    assert quote.effective_price == 100


def test_an_offer_that_raises_the_price_is_not_honoured():
    """A campaign that costs the customer more is a mistake, not an offer."""

    quote = quote_promotion(_promotion(promo_price=150), _context(), base_price=100)

    assert quote.eligible is False
    assert quote.effective_price == 100


def test_an_offer_carrying_only_a_discount_field_prices_nothing():
    """Authoring fields are not pricing authority, and must not be guessed at.

    `discount_type`/`discount_value` describe what an editor typed; the
    promoted price is what the customer is charged. Inferring one from the
    other here would let an unreviewed edit move a live price.
    """

    quote = quote_promotion(
        {
            "id": "cmp_authoring_only",
            "status": "active",
            "tenant_id": str(TENANT),
            "store_id": str(STORE),
            "discount_type": "amount",
            "discount_value": 20,
        },
        _context(),
        base_price=100,
    )

    assert quote.eligible is False
    assert quote.effective_price == 100


def test_the_cheapest_eligible_offer_is_the_one_selected():
    """Two offers must not stack, and the customer gets the better one."""

    cheap = _promotion(id="cmp_cheap", promo_price=50)
    dear = _promotion(id="cmp_dear", promo_price=90)

    selected = select_promotion_quote([dear, cheap], _context(), base_price=100)

    assert selected.eligible
    assert selected.promotion_ref == "cmp_cheap"
    assert selected.effective_price == 50, "the two offers stacked, or the dearer one won"


def test_an_item_with_no_eligible_offer_keeps_its_base_price():
    projection = project_item_price([_promotion(status="draft")], _context(), base_price=100)

    assert projection.effective_price == 100
    assert projection.discount == 0
    assert not projection.promotion_ref


def test_a_projected_discount_always_names_the_offer_that_granted_it():
    projection = project_item_price([_promotion()], _context(), base_price=100)

    if projection.effective_price < projection.base_price:
        assert projection.promotion_ref, "a discount was applied with no offer recorded"


def test_a_claim_the_promotion_does_not_support_is_refused():
    """A browser naming an offer it is not entitled to must not be believed.

    `preferred_ref` is the client's stated preference. It may break a tie
    between offers the server itself found eligible; it may not introduce one.
    """

    selected = select_promotion_quote([_promotion()], _context(), base_price=100, preferred_ref="cmp_does_not_exist")

    assert selected.promotion_ref == "cmp_gate", "a client-named offer displaced the server's own"
    assert selected.effective_price == 80


def test_a_preference_cannot_beat_a_cheaper_offer():
    """The client's pick is a tie-break, not an override of the better price."""

    selected = select_promotion_quote(
        [_promotion(id="cmp_cheap", promo_price=50), _promotion(id="cmp_dear", promo_price=90)],
        _context(),
        base_price=100,
        preferred_ref="cmp_dear",
    )

    assert selected.promotion_ref == "cmp_cheap"
    assert selected.effective_price == 50, "the client chose its own price by naming an offer"


# --- schedule: timezone and bounds -----------------------------------------


def test_the_last_day_of_an_offer_lasts_until_the_end_of_that_day():
    """A date-only end is inclusive; midnight would cut the last day off."""

    promotion = _promotion(timezone="Asia/Taipei", starts_at="2026-08-01", ends_at="2026-08-13")
    late = datetime(2026, 8, 13, 15, 30, tzinfo=timezone.utc)  # 23:30 in Taipei

    assert evaluate_promotion(promotion, _context(now=late)).eligible is True


def test_an_offer_is_over_once_its_last_day_is_over():
    promotion = _promotion(timezone="Asia/Taipei", starts_at="2026-08-01", ends_at="2026-08-13")
    next_day = datetime(2026, 8, 13, 16, 30, tzinfo=timezone.utc)  # 00:30 on the 14th in Taipei

    assert evaluate_promotion(promotion, _context(now=next_day)).eligible is False


def test_the_boundary_is_read_in_the_offers_timezone_not_the_servers():
    """The same instant is inside the offer in Taipei and outside it in UTC."""

    instant = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)  # 04:00 on the 14th in Taipei
    ends_on_the_13th = _promotion(ends_at="2026-08-13")

    taipei = evaluate_promotion({**ends_on_the_13th, "timezone": "Asia/Taipei"}, _context(now=instant))
    utc = evaluate_promotion({**ends_on_the_13th, "timezone": "UTC"}, _context(now=instant))

    assert taipei.eligible is False, "Taipei was already past the last day"
    assert utc.eligible is True, "UTC was still inside the last day"


def test_an_unusable_timezone_does_not_take_pricing_down():
    """A bad timezone string is an authoring mistake, not an outage."""

    result = evaluate_promotion(_promotion(timezone="Mars/Olympus_Mons", ends_at="2099-01-01"), _context())

    assert result.eligible is True


# --- authored push copy ----------------------------------------------------


def test_campaign_copy_is_used_only_while_its_offer_is_live():
    entry = {
        "campaign_copy": "活動中的促購文案",
        "campaign_offer_id": "offer-1",
        "base_copy": "常青文案",
    }
    item = {"description": "菜單描述"}

    assert resolve_copy(item, entry, live_offer_ids={"offer-1"}) == ("活動中的促購文案", STATUS_CAMPAIGN)
    assert resolve_copy(item, entry, live_offer_ids=set()) == ("常青文案", STATUS_BASE)


def test_push_copy_falls_back_to_description_when_no_authored_copy_exists():
    assert resolve_copy({"description": "真實菜單描述"}, {}, live_offer_ids=set()) == (
        "真實菜單描述",
        STATUS_DESCRIPTION,
    )


def test_member_only_live_offers_are_not_visible_to_guest_push_copy():
    offers = [{"offer_id": "guest-offer"}, {"offer_id": "member-offer", "member_only": True}]

    assert active_offer_ids(offers, audience="guest") == {"guest-offer"}
    assert active_offer_ids(offers, audience="member") == {"guest-offer", "member-offer"}


# --- persistence -----------------------------------------------------------


def _campaign_payload(**overrides) -> dict:
    """A campaign the authoring rules accept.

    `preview_campaign` requires a name, a start, at least one placement and
    exactly one promotion rule; a payload missing any of them is refused before
    anything is stored, which is what the rejection test below relies on.
    """

    payload = {
        "name": f"gate-{uuid.uuid4().hex[:10]}",
        "objective": "promote_item",
        "audience": "all",
        "schedule": {"starts_at": "2026-08-14T00:00:00+08:00"},
        "placements": ["menu_card"],
        "promotion_rules": [
            {
                "type": "fixed_item_price",
                "item_ids": [f"item-{uuid.uuid4().hex[:8]}"],
                "promotion_price": 50,
            }
        ],
        "store_ids": [str(STORE)],
    }
    payload.update(overrides)
    return payload


def _on_postgres() -> bool:
    return str(os.environ.get("DATABASE_BACKEND", "")).strip() == "postgresql" and postgres_utils.use_postgres()


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="campaign versions are stored in PostgreSQL")
def test_two_editors_cannot_both_win_with_the_same_expected_version():
    """The second writer has to be told, not silently overwrite the first."""

    from models.commercial_scope import CommercialScope
    from modules.promotion.application import create_campaign_draft, revise_campaign_draft

    scope = CommercialScope(TENANT, STORE)
    payload = _campaign_payload()

    created = create_campaign_draft(payload, scope, actor_id="gate-test")
    try:
        revise_campaign_draft(
            created.campaign_id,
            {**payload, "name": f"{payload['name']}-first"},
            scope,
            expected_version=created.version,
            actor_id="editor-one",
        )

        with pytest.raises(contracts.CampaignConflictError):
            revise_campaign_draft(
                created.campaign_id,
                {**payload, "name": f"{payload['name']}-second"},
                scope,
                expected_version=created.version,
                actor_id="editor-two",
            )
    finally:
        _purge(created.campaign_id)


def _purge(*campaign_ids: str) -> None:
    """Remove everything a campaign writes: definition, versions, projection, trail.

    `campaign_versions` cascades from `campaign_definitions`; the published
    projection in `promotion_records` and the admin audit rows do not, and a
    leftover projection would price real carts.
    """

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        for campaign_id in campaign_ids:
            cur.execute(
                "DELETE FROM promotion_records WHERE tenant_id = %s AND store_id = %s AND promotion_id = %s",
                (str(TENANT), str(STORE), campaign_id),
            )
            cur.execute(
                "DELETE FROM admin_audit_logs WHERE target_type = 'campaign' AND target_id = %s",
                (campaign_id,),
            )
            cur.execute(
                "DELETE FROM campaign_definitions WHERE tenant_id = %s AND store_id = %s AND campaign_id = %s",
                (str(TENANT), str(STORE), campaign_id),
            )
        conn.commit()


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="campaigns are published into PostgreSQL")
def test_a_campaign_starting_later_goes_on_air_later():
    """Publishing is a request to go live, not an instruction to go live now."""

    from modules.promotion.application import publish_campaign

    scope = CommercialScope(TENANT, STORE)
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    payload = _campaign_payload(schedule={"starts_at": (now + timedelta(days=7)).date().isoformat()})

    published = publish_campaign(payload, scope, actor_id="gate-test", now=now)
    try:
        assert published.status == "scheduled", published.status
    finally:
        _purge(published.campaign_id)


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="campaigns are published into PostgreSQL")
def test_a_scheduled_campaign_is_projected_but_does_not_price_yet():
    """The projection carries a scheduled campaign; the clock decides, not the flag.

    `project_legacy` writes `status: active` for a campaign that is merely
    `scheduled`, so anything that trusts that field alone would show — and
    price — an offer before it starts. What actually holds the line is
    `start_at` on the projected record, so that is what this checks: read the
    record the Kiosk reads, and price against it before and after the start.
    """

    from modules.promotion.adapters import promotion as promotion_projection
    from modules.promotion.application import publish_campaign

    scope = CommercialScope(TENANT, STORE)
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    starts_at = (now + timedelta(days=7)).date().isoformat()
    payload = _campaign_payload(schedule={"starts_at": starts_at})

    published = publish_campaign(payload, scope, actor_id="gate-test", now=now)
    try:
        projected = [
            record
            for record in promotion_projection.list_promotions_scoped(scope)
            if str(record.get("id")) == published.campaign_id
        ]
        assert projected, "a published campaign never reached the projection the Kiosk reads"
        record = projected[0]
        item_id = str(payload["promotion_rules"][0]["item_ids"][0])

        before = quote_promotion(record, _context(now=now, item_id=item_id), base_price=100)
        after = quote_promotion(record, _context(now=now + timedelta(days=8), item_id=item_id), base_price=100)

        assert before.eligible is False, "a scheduled campaign priced an item before it started"
        assert before.code == "promotion_not_started"
        assert after.eligible is True, "the campaign never started"
        assert after.effective_price == 50
    finally:
        _purge(published.campaign_id)


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="campaigns are published into PostgreSQL")
def test_a_rejected_publication_leaves_no_campaign_behind():
    """Half a publication is worse than none — the operator would not know."""

    from modules.promotion.application import list_campaigns, publish_campaign

    scope = CommercialScope(TENANT, STORE)
    before = {snapshot.campaign_id for snapshot in list_campaigns(scope)}

    with pytest.raises(ValueError):
        publish_campaign({"store_ids": [str(STORE)]}, scope, actor_id="gate-test")

    after = {snapshot.campaign_id for snapshot in list_campaigns(scope)}
    assert after == before, f"a refused publication stored {after - before}"
