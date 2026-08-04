"""Push copy is authored in Admin and only looked up at request time."""

import importlib
from datetime import date

import pytest


@pytest.fixture
def service():
    from services import push_copy_service
    importlib.reload(push_copy_service)
    return push_copy_service


ITEM = {"id": "MCD001", "name": "滿福堡", "category": "早餐", "description": "經典早餐堡，適合早餐時段快速點餐。"}


def test_campaign_copy_is_served_while_its_offer_is_live(service):
    entry = {"base_copy": "經典蛋香配上煙燻火腿。", "campaign_copy": "早餐買一送一！", "campaign_offer_id": "off_1"}

    text, status = service.resolve_copy(ITEM, entry, live_offer_ids={"off_1"})

    assert text == "早餐買一送一！"
    assert status == service.STATUS_CAMPAIGN


def test_campaign_copy_stops_being_served_once_its_offer_ends(service):
    """The whole point of binding copy to an offer: ended campaigns cannot outlive themselves."""

    entry = {"base_copy": "經典蛋香配上煙燻火腿。", "campaign_copy": "早餐買一送一！", "campaign_offer_id": "off_1"}

    text, status = service.resolve_copy(ITEM, entry, live_offer_ids=set())

    assert text == "經典蛋香配上煙燻火腿。"
    assert status == service.STATUS_BASE


def test_campaign_copy_without_binding_never_serves(service):
    entry = {"base_copy": "經典蛋香。", "campaign_copy": "限時優惠！", "campaign_offer_id": ""}

    text, status = service.resolve_copy(ITEM, entry, live_offer_ids={"off_1"})

    assert text == "經典蛋香。"
    assert status == service.STATUS_BASE


def test_missing_copy_falls_back_to_menu_description(service):
    text, status = service.resolve_copy(ITEM, None, live_offer_ids=set())

    assert text == "經典早餐堡，適合早餐時段快速點餐。"
    assert status == service.STATUS_DESCRIPTION


def test_active_offer_ids_hides_member_only_offers_from_guests(service):
    offers = [
        {"offer_id": "off_pub"},
        {"offer_id": "off_mem", "member_only": True},
    ]

    assert service.active_offer_ids(offers, audience="guest") == {"off_pub"}
    assert service.active_offer_ids(offers, audience="member") == {"off_pub", "off_mem"}


MENU = [
    {"id": "A1", "category": "早餐"},
    {"id": "B1", "category": "飲料"},
    {"id": "C1", "category": "點心"},
]


def test_scope_all_admits_every_item(service, monkeypatch):
    monkeypatch.setattr(service.config, "get", lambda k, d=None: {"AI_PUSH_SCOPE_MODE": "all"}.get(k, d))

    assert service.eligible_item_ids(MENU, {}) == ["A1", "B1", "C1"]


def test_scope_categories_filters_to_selected_categories(service, monkeypatch):
    monkeypatch.setattr(service.config, "get", lambda k, d=None: {
        "AI_PUSH_SCOPE_MODE": "categories",
        "AI_PUSH_SCOPE_CATEGORIES": ["早餐", "點心"],
    }.get(k, d))

    assert service.eligible_item_ids(MENU, {}) == ["A1", "C1"]


def test_scope_categories_with_empty_list_does_not_silently_push_nothing(service, monkeypatch):
    """An unconfigured category list must not mean 'no item is ever eligible'."""

    monkeypatch.setattr(service.config, "get", lambda k, d=None: {
        "AI_PUSH_SCOPE_MODE": "categories",
        "AI_PUSH_SCOPE_CATEGORIES": [],
    }.get(k, d))

    assert service.eligible_item_ids(MENU, {}) == ["A1", "B1", "C1"]


def test_scope_new_items_respects_the_new_item_window(service, monkeypatch):
    monkeypatch.setattr(service.config, "get", lambda k, d=None: {"AI_PUSH_SCOPE_MODE": "new_items"}.get(k, d))
    rows = {
        "A1": {"is_new_item": True, "new_until": "2026-12-31"},
        "B1": {"is_new_item": True, "new_until": "2026-01-01"},   # window has closed
        "C1": {"is_new_item": False, "new_until": ""},
    }

    assert service.eligible_item_ids(MENU, rows, today=date(2026, 7, 29)) == ["A1"]


def test_scope_popular_keeps_popularity_order(service, monkeypatch):
    monkeypatch.setattr(service.config, "get", lambda k, d=None: {"AI_PUSH_SCOPE_MODE": "popular"}.get(k, d))

    assert service.eligible_item_ids(MENU, {}, popular_ids=["C1", "A1"]) == ["C1", "A1"]


def test_unknown_scope_mode_falls_back_to_all(service, monkeypatch):
    monkeypatch.setattr(service.config, "get", lambda k, d=None: {"AI_PUSH_SCOPE_MODE": "nonsense"}.get(k, d))

    assert service.scope_mode() == "all"
    assert service.eligible_item_ids(MENU, {}) == ["A1", "B1", "C1"]
