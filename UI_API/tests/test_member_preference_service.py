import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
    {"id": "MCD030", "name": "可口可樂(中)", "price": 35, "category": "飲料"},
]


@pytest.fixture
def services(monkeypatch):
    from repositories import menu_repository
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))
    from services import member_service, member_preference_service
    importlib.reload(member_service)
    importlib.reload(member_preference_service)
    monkeypatch.setattr(member_service.menu_repository, "get_menu", lambda: list(MENU))
    return member_preference_service


def _member():
    return {
        "phone": "0912345678",
        "nickname": "小明",
        "visit_count": 4,
        "total_spend": 800,
        "item_freq": {"MCD001": 5, "MCD012": 3, "MCD999": 99},
        "category_freq": {"點心": 7, "超值全餐": 5},
        "pair_freq": {"MCD001|MCD012": 4, "MCD001|MCD999": 9},
        "recent_item_ids": ["MCD012", "MCD001"],
        "orders": [
            {"cart_ids": ["MCD030"], "order_status": "cancelled", "is_completed": False},
            {"cart_ids": ["MCD001", "MCD012", "MCD001"], "order_status": "completed"},
        ],
    }


def test_build_preference_summary_masks_phone_and_filters_menu_items(services):
    summary = services.build_preference_summary(_member())
    assert summary["has_member"] is True
    assert summary["phone_masked"] == "0912-***-678"
    assert summary["nickname"] == "小明"
    assert summary["avg_spend"] == 200
    assert summary["usual_item_ids"] == ["MCD001", "MCD012"]
    assert summary["recent_item_ids"] == ["MCD012", "MCD001"]
    assert summary["last_order_item_ids"] == ["MCD001", "MCD012"]
    assert summary["last_order_items"] == [
        {"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐"},
        {"id": "MCD012", "name": "薯條(中)", "category": "點心"},
    ]
    assert summary["preferred_categories"] == ["點心", "超值全餐"]
    assert summary["frequent_pairs"] == [{
        "item_ids": ["MCD001", "MCD012"],
        "items": [
            {"id": "MCD001", "name": "大麥克套餐", "category": "超值全餐"},
            {"id": "MCD012", "name": "薯條(中)", "category": "點心"},
        ],
        "count": 4,
    }]


def test_empty_preference_summary_for_guest(services):
    summary = services.build_preference_summary(None)
    assert summary["has_member"] is False
    assert summary["usual_item_ids"] == []
    assert summary["phone_masked"] == ""


def test_format_member_prompt_section_omits_full_phone(services):
    section = services.format_member_prompt_section(services.build_preference_summary(_member()))
    assert "會員偏好摘要" in section
    assert "會員常點 ID" in section
    assert "MCD001｜大麥克套餐｜超值全餐｜常點 5 次" in section
    assert "最近完成訂單 ID" in section
    assert "MCD012｜薯條(中)｜點心" in section
    assert "取得明確確認後才輸出 cart_actions" in section
    assert "常見搭配：大麥克套餐 + 薯條(中)" in section
    assert "大麥克套餐" in section
    assert "0912345678" not in section
    assert services.format_member_prompt_section(services.empty_preference_summary()) == ""
