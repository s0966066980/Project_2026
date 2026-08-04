import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐", "official_image_url": "/x.jpg"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
    {"id": "MCD030", "name": "可口可樂(中)", "price": 35, "category": "飲料"},
]


@pytest.fixture
def svc(tmp_path, monkeypatch):
    from repositories import member_repository, menu_repository
    importlib.reload(member_repository)
    monkeypatch.setattr(member_repository, "MEMBERS_PATH", str(tmp_path / "members.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))
    from services import member_service
    importlib.reload(member_service)
    member_service._session_member.clear()
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    return member_service


def _member(freq):
    return {"phone": "0912345678", "nickname": "小明", "visit_count": 3,
            "total_spend": 600, "item_freq": dict(freq), "orders": []}


def test_build_usuals_sorted_and_whitelisted(svc):
    m = _member({"MCD012": 6, "MCD001": 8, "MCD999": 99})  # MCD999 不在菜單 → 過濾
    usuals = svc.build_usuals(m)
    assert [u["id"] for u in usuals] == ["MCD001", "MCD012"]
    assert usuals[0]["count"] == 8
    assert usuals[0]["image"] == "/x.jpg"
    assert usuals[0]["name"] == "大麥克套餐"


def test_build_usuals_respects_limit(svc):
    m = _member({"MCD001": 8, "MCD012": 6, "MCD030": 5})
    assert len(svc.build_usuals(m, limit=2)) == 2


def test_member_top_ids(svc):
    m = _member({"MCD001": 8, "MCD012": 6, "MCD030": 5})
    assert svc.member_top_ids(m, 2) == ["MCD001", "MCD012"]


def test_member_push_context(svc):
    m = _member({"MCD001": 8})
    ctx = svc.member_push_context(m)
    assert "大麥克套餐" in ctx and "小明" in ctx
    assert svc.member_push_context(_member({})) == ""


def test_finalize_checkout_updates_profile(svc):
    svc.register("s1", "0912345678", "小明")
    out = svc.finalize_checkout("s1", ["MCD001", "MCD012", "MCD001"], 200, False)
    assert out["visit_count"] == 1
    assert out["total_spend"] == 200
    # 去重 → 光臨次數：MCD001 與 MCD012 各 +1
    assert out["item_freq"] == {"MCD001": 1, "MCD012": 1}
    assert out["category_freq"] == {"超值全餐": 1, "點心": 1}
    assert out["pair_freq"] == {"MCD001|MCD012": 1}
    assert out["recent_item_ids"] == ["MCD001", "MCD012"]
    assert out["preference_updated_at"]
    assert len(out["orders"]) == 1 and out["orders"][0]["total"] == 200
    assert out["orders"][0]["order_status"] == "completed"
    assert out["orders"][0]["is_completed"] is True
    assert out["orders"][0]["recommendation_success"] is False
    assert svc.get_session_member("s1") is None  # 綁定已清除


def test_finalize_checkout_uses_cart_item_quantities_when_available(svc):
    svc.register("s1", "0912345678", "小明")
    out = svc.finalize_checkout(
        "s1",
        ["MCD001", "MCD012"],
        355,
        True,
        [
            {"id": "MCD001", "quantity": 2},
            {"id": "MCD012", "quantity": 1},
        ],
    )
    assert out["item_freq"] == {"MCD001": 2, "MCD012": 1}
    assert out["category_freq"] == {"超值全餐": 2, "點心": 1}
    assert out["pair_freq"] == {"MCD001|MCD012": 1}
    assert out["orders"][0]["cart_ids"] == ["MCD001", "MCD001", "MCD012"]
    assert out["orders"][0]["cart_items"][0]["quantity"] == 2


def test_finalize_checkout_updates_pair_count_with_quantities(svc):
    svc.register("s1", "0912345678", "小明")
    out = svc.finalize_checkout(
        "s1",
        ["MCD001", "MCD012"],
        400,
        True,
        [
            {"id": "MCD001", "quantity": 2},
            {"id": "MCD012", "quantity": 2},
            {"id": "MCD030", "quantity": 1},
        ],
    )
    assert out["pair_freq"]["MCD001|MCD012"] == 2
    assert out["pair_freq"]["MCD001|MCD030"] == 1
    assert out["pair_freq"]["MCD012|MCD030"] == 1
    assert out["recent_item_ids"] == ["MCD001", "MCD012", "MCD030"]


def test_finalize_checkout_no_member_returns_none(svc):
    assert svc.finalize_checkout("nobody", ["MCD001"], 100, True) is None


def test_finalize_checkout_orders_capped(svc, monkeypatch):
    monkeypatch.setattr(svc.config, "get", lambda k, d=None: 2 if k == "MEMBER_ORDERS_KEEP" else d)
    svc.register("s1", "0912345678", "小明")
    for _ in range(3):
        svc.bind_session("s1", "0912345678")
        svc.finalize_checkout("s1", ["MCD001"], 100, True)
    m = svc.member_repository.get_member("0912345678")
    assert len(m["orders"]) == 2


def test_admin_clear_records_clears_preference_stats(svc):
    svc.register("s1", "0912345678", "小明")
    svc.finalize_checkout("s1", ["MCD001", "MCD012"], 200, True)
    assert svc.admin_clear_records("0912345678") is True
    m = svc.member_repository.get_member("0912345678")
    assert m["item_freq"] == {}
    assert m["category_freq"] == {}
    assert m["pair_freq"] == {}
    assert m["recent_item_ids"] == []
    assert m["preference_updated_at"] == ""


def test_record_abandoned_order_marks_incomplete(svc):
    svc.register("s1", "0912345678", "小明")
    out = svc.record_abandoned_order("s1", ["MCD001"], 155, "home_button")
    assert out["visit_count"] == 0
    assert out["total_spend"] == 0
    assert out["orders"][0]["order_status"] == "cancelled"
    assert out["orders"][0]["is_completed"] is False
    assert out["orders"][0]["cancel_reason"] == "home_button"
    assert svc.get_session_member("s1") is None


def test_build_history_treats_legacy_is_success_as_completed(svc):
    member = _member({})
    member["orders"] = [{
        "timestamp": "2026-06-30T12:00:00",
        "cart_ids": ["MCD001"],
        "total": 155,
        "is_success": False,
    }]
    history = svc.build_history(member)
    assert history[0]["is_completed"] is True
    assert history[0]["order_status"] == "completed"
    assert history[0]["recommendation_success"] is False
