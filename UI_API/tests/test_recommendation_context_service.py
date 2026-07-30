import importlib
import asyncio

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
]


@pytest.fixture
def ctx_service(tmp_path, monkeypatch):
    from repositories import member_repository, menu_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))

    from services import member_service, member_preference_service, recommendation_context_service
    importlib.reload(member_service)
    importlib.reload(member_preference_service)
    importlib.reload(recommendation_context_service)
    member_service._session_member.clear()
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    monkeypatch.setattr(recommendation_context_service, "get_top_items", lambda n=3: [MENU[1]])
    monkeypatch.setattr(
        recommendation_context_service.rag_offer_service,
        "load_active_offers",
        lambda menu_items: [],
    )
    monkeypatch.setattr(
        recommendation_context_service.recommendation_feedback_service,
        "build_feedback_context",
        lambda session_id, member_phone_masked="": {
            "ignored_item_ids": [],
            "ignored_offer_ids": [],
            "penalty_by_item_id": {},
            "penalty_by_offer_id": {},
            "exclude_item_ids": [],
            "window_minutes": 0,
        },
    )
    monkeypatch.setattr(
        recommendation_context_service.availability_service,
        "build_availability_context",
        lambda menu_items: {
            "enabled": True,
            "exclude_item_ids": [],
            "low_stock_item_ids": [],
            "unavailable_item_ids": [],
            "low_stock_penalty": 0,
        },
    )
    return recommendation_context_service, member_service


def test_build_context_for_guest(ctx_service):
    recommendation_context_service, _ = ctx_service
    context = asyncio.run(recommendation_context_service.build_context(
        "guest-session",
        exclude_ids=["MCD001", "MCD001"],
        surface="ai_push",
        menu_items=list(MENU),
    ))
    assert context["audience"] == "guest"
    assert context["member"]["has_member"] is False
    assert context["preferences"]["usual_item_ids"] == []
    assert context["global"]["popular_item_ids"] == ["MCD012"]
    assert context["controls"]["exclude_item_ids"] == ["MCD001"]
    assert context["controls"]["surface"] == "ai_push"
    assert context["feedback"]["ignored_item_ids"] == []
    assert context["availability"]["enabled"] is True
    assert context["rag"]["offers"] == []


def test_build_context_merges_availability_exclusions(ctx_service, monkeypatch):
    recommendation_context_service, _ = ctx_service
    monkeypatch.setattr(
        recommendation_context_service.availability_service,
        "build_availability_context",
        lambda menu_items: {
            "enabled": True,
            "exclude_item_ids": ["MCD012"],
            "low_stock_item_ids": [],
            "unavailable_item_ids": ["MCD012"],
            "low_stock_penalty": 1,
        },
    )

    context = asyncio.run(recommendation_context_service.build_context(
        "guest-session",
        exclude_ids=["MCD001"],
        menu_items=list(MENU),
    ))

    assert context["controls"]["exclude_item_ids"] == ["MCD001", "MCD012"]


def test_build_context_for_member(ctx_service):
    recommendation_context_service, member_service = ctx_service
    member_service.register("s1", "0912345678", "小明")
    member = member_service.member_repository.get_member("0912345678")
    member["item_freq"] = {"MCD001": 3}
    member["orders"] = [{"cart_ids": ["MCD001", "MCD012"], "order_status": "completed"}]
    member_service.member_repository.upsert_member(member)

    context = asyncio.run(recommendation_context_service.build_context("s1", menu_items=list(MENU)))
    assert context["audience"] == "member"
    assert context["member"]["nickname"] == "小明"
    assert context["member"]["phone_masked"] == "0912-***-678"
    assert context["preferences"]["usual_item_ids"] == ["MCD001"]
    assert context["preferences"]["last_order_item_ids"] == ["MCD001", "MCD012"]
    assert "0912345678" not in recommendation_context_service.member_prompt_section(context)


def test_build_context_includes_validated_rag_offers(ctx_service, monkeypatch):
    recommendation_context_service, _ = ctx_service
    offers = [{
        "offer_id": "member_fries",
        "title": "會員薯條活動",
        "member_only": True,
        "item_ids": ["MCD012"],
    }]
    monkeypatch.setattr(
        recommendation_context_service.rag_offer_service,
        "load_active_offers",
        lambda menu_items: offers,
    )

    context = asyncio.run(recommendation_context_service.build_context("s1", menu_items=list(MENU)))

    assert context["rag"]["offers"] == offers


def test_build_context_includes_rag_text_when_query_is_enabled(ctx_service, monkeypatch):
    recommendation_context_service, _ = ctx_service

    class FakeRag:
        async def query(self, text, top_k=None, *, scope=None):
            assert text == "會員優惠"
            assert top_k == 2
            return "【RAG 補充資訊】會員薯條活動"

    from services import rag_provider
    monkeypatch.setattr(rag_provider, "get_rag", lambda: FakeRag())

    def fake_config_get(key, default=None):
        if key == "RAG_ENABLED":
            return True
        if key == "AI_PUSH_PRIORITY_CATS":
            return []
        return default

    monkeypatch.setattr(recommendation_context_service.config, "get", fake_config_get)

    context = asyncio.run(recommendation_context_service.build_context(
        "s1",
        rag_query="會員優惠",
        rag_top_k=2,
        menu_items=list(MENU),
    ))

    assert context["rag"]["context"] == "【RAG 補充資訊】會員薯條活動"
