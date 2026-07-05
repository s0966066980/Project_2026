import importlib
from datetime import datetime


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD900", "name": "豬肉滿福堡", "price": 75, "category": "早餐", "available_categories": ["早餐"]},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
]


def _service(tmp_path, monkeypatch):
    from repositories import availability_repository, menu_repository
    importlib.reload(availability_repository)
    importlib.reload(menu_repository)
    monkeypatch.setattr(availability_repository, "AVAILABILITY_PATH", str(tmp_path / "availability.json"))
    monkeypatch.setattr(menu_repository, "get_menu", lambda: list(MENU))

    from services import availability_service
    importlib.reload(availability_service)
    monkeypatch.setattr(availability_service.menu_repository, "get_menu", lambda: list(MENU))
    return availability_service, availability_repository


def test_default_availability_excludes_breakfast_items_after_breakfast(tmp_path, monkeypatch):
    availability_service, _ = _service(tmp_path, monkeypatch)

    context = availability_service.build_availability_context(
        list(MENU),
        now=datetime(2026, 7, 3, 12, 0),
    )

    assert context["enabled"] is True
    assert context["service_period"] == "regular"
    assert context["time_unavailable_item_ids"] == ["MCD900"]
    assert context["exclude_item_ids"] == ["MCD900"]


def test_manual_sold_out_disabled_and_low_stock_are_normalized(tmp_path, monkeypatch):
    availability_service, availability_repository = _service(tmp_path, monkeypatch)
    availability_repository.save_availability({
        "store_id": "store-a",
        "service_period": "breakfast",
        "sold_out_item_ids": ["MCD001", "MISSING"],
        "low_stock_item_ids": ["MCD012"],
        "store_disabled_item_ids": ["MCD900"],
    })

    context = availability_service.build_availability_context(list(MENU), now=datetime(2026, 7, 3, 8, 0))

    assert context["store_id"] == "store-a"
    assert context["service_period"] == "breakfast"
    assert context["sold_out_item_ids"] == ["MCD001"]
    assert context["low_stock_item_ids"] == ["MCD012"]
    assert context["store_disabled_item_ids"] == ["MCD900"]
    assert context["exclude_item_ids"] == ["MCD001", "MCD900"]


def test_save_admin_state_returns_item_status_rows(tmp_path, monkeypatch):
    availability_service, _ = _service(tmp_path, monkeypatch)

    state = availability_service.save_admin_state({
        "store_id": "store-b",
        "service_period": "regular",
        "sold_out_item_ids": ["MCD001"],
        "low_stock_item_ids": ["MCD012"],
        "store_disabled_item_ids": [],
    })
    by_id = {row["id"]: row for row in state["items"]}

    assert state["store_id"] == "store-b"
    assert by_id["MCD001"]["status"] == "sold_out"
    assert by_id["MCD012"]["status"] == "low_stock"
    assert by_id["MCD900"]["time_unavailable"] is True
