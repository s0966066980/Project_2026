import importlib

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155},
    {"id": "MCD012", "name": "薯條(中)", "price": 45},
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


def _seed(svc, phone, nick, freq, visit, spend):
    svc.member_repository.upsert_member({
        "phone": phone, "nickname": nick, "created_at": "2026-03-01T00:00:00",
        "visit_count": visit, "total_spend": spend, "last_visit_at": "2026-06-20T00:00:00",
        "item_freq": dict(freq),
        "orders": [{"timestamp": "2026-06-20T00:00:00", "cart_ids": list(freq), "total": spend, "is_success": True}],
    })


def _seed_mixed_orders(svc):
    svc.member_repository.upsert_member({
        "phone": "0912345678",
        "nickname": "小明",
        "created_at": "2026-03-01T00:00:00",
        "visit_count": 1,
        "total_spend": 155,
        "last_visit_at": "2026-06-21T00:00:00",
        "item_freq": {"MCD001": 1},
        "orders": [
            {
                "timestamp": "2026-06-20T00:00:00",
                "cart_ids": ["MCD001"],
                "total": 155,
                "order_status": "completed",
                "is_completed": True,
                "recommendation_success": True,
            },
            {
                "timestamp": "2026-06-21T00:00:00",
                "cart_ids": ["MCD012"],
                "total": 45,
                "order_status": "cancelled",
                "is_completed": False,
                "cancel_reason": "home_button",
            },
        ],
    })


def test_admin_list(svc):
    _seed(svc, "0912345678", "小明", {"MCD001": 8, "MCD012": 6}, 12, 3720)
    rows = svc.admin_list()
    assert len(rows) == 1
    r = rows[0]
    assert r["phone_masked"] == "0912-***-678"
    assert r["nickname"] == "小明"
    assert r["favorites"] == ["大麥克套餐", "薯條(中)"]
    assert r["completed_order_count"] == 1
    assert r["incomplete_order_count"] == 0
    assert r["completed_spend"] == 3720


def test_admin_detail(svc):
    _seed(svc, "0912345678", "小明", {"MCD001": 8, "MCD012": 6}, 12, 3720)
    d = svc.admin_detail("0912345678")
    assert d["phone_masked"] == "0912-***-678"
    assert d["avg_spend"] == 310  # 3720 // 12
    assert d["avg_completed_spend"] == 3720
    assert d["favorites_ranked"][0] == {"id": "MCD001", "name": "大麥克套餐", "count": 8}
    assert len(d["orders"]) == 1
    assert d["orders"][0]["items"][0]["name"] == "大麥克套餐"


def test_admin_metrics_distinguish_completed_and_incomplete(svc):
    _seed_mixed_orders(svc)
    row = svc.admin_list()[0]
    assert row["completed_order_count"] == 1
    assert row["incomplete_order_count"] == 1
    assert row["completed_spend"] == 155
    assert row["avg_completed_spend"] == 155
    assert row["recommendation_hit_count"] == 1
    assert row["last_order_status"] == "cancelled"

    detail = svc.admin_detail("0912345678")
    assert detail["orders"][0]["is_completed"] is False
    assert detail["orders"][0]["cancel_reason"] == "home_button"
    assert detail["orders"][0]["items"][0]["name"] == "薯條(中)"
    assert detail["orders"][1]["is_completed"] is True


def test_admin_detail_missing(svc):
    assert svc.admin_detail("0900000000") is None
