"""Store-scoped menu catalog master (ADR-0018 / issues #1–#6)."""

from __future__ import annotations

import importlib
from pathlib import Path

import numpy as np
import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
from models.commercial_scope import LEGACY_DEFAULT_TENANT_ID, LEGACY_DEFAULT_STORE_ID
from uuid import UUID


SEED_MENU = [
    {
        "id": "MCD001",
        "name": "大麥克",
        "category": "超值全餐",
        "price": 80,
        "description": "經典漢堡",
        "image": "https://example.com/a.jpg",
        "aliases": ["big mac"],
    },
    {
        "id": "MCD900",
        "name": "豬肉滿福堡",
        "category": "早餐",
        "price": 55,
        "description": "早餐堡",
        "available_categories": ["早餐"],
    },
]


@pytest.fixture()
def catalog(tmp_path, monkeypatch):
    seed_path = tmp_path / "menu.json"
    seed_path.write_text(
        __import__("json").dumps(SEED_MENU, ensure_ascii=False),
        encoding="utf-8",
    )
    data_dir = tmp_path / "learning"
    data_dir.mkdir()

    import config
    from repositories import menu_repository, postgres_utils
    from services import menu_catalog_service, object_storage_service

    importlib.reload(menu_repository)
    importlib.reload(menu_catalog_service)

    monkeypatch.setattr(config, "MENU_JSON_PATH", str(seed_path), raising=False)
    monkeypatch.setattr(config, "LEARNING_DATA_DIR", str(data_dir), raising=False)
    monkeypatch.setattr(menu_repository, "config", config)
    monkeypatch.setattr(postgres_utils, "use_postgres", lambda: False)
    menu_repository.reset_for_tests()
    object_storage_service.reset_for_tests(backend="memory", root=tmp_path / "objs")

    return menu_repository, menu_catalog_service, LEGACY_DEFAULT_SCOPE


def test_empty_store_seeds_once_and_does_not_overwrite(catalog, tmp_path):
    menu_repository, menu_catalog_service, scope = catalog
    first = menu_catalog_service.ensure_seeded(scope)
    assert first["seeded"] is True
    assert first["count"] == 2
    items = menu_catalog_service.list_catalog(scope)
    assert {row["id"] for row in items} == {"MCD001", "MCD900"}
    assert any(row.get("aliases") == ["big mac"] for row in items)

    menu_catalog_service.update_item(scope, "MCD001", {"name": "店家大麥克", "price": 99})
    second = menu_catalog_service.ensure_seeded(scope)
    assert second["skipped"] is True
    updated = menu_catalog_service.get_item(scope, "MCD001")
    assert updated["name"] == "店家大麥克"
    assert updated["price"] == 99


def test_scoped_isolation_between_stores(catalog):
    menu_repository, menu_catalog_service, scope_a = catalog
    scope_b = CommercialScope(
        tenant_id=LEGACY_DEFAULT_TENANT_ID,
        store_id=UUID("00000000-0000-4000-8000-000000000099"),
    )
    menu_catalog_service.ensure_seeded(scope_a)
    menu_catalog_service.create_item(
        scope_b,
        {"name": "只在 B 店", "category": "點心", "price": 30, "description": ""},
    )
    ids_a = {row["id"] for row in menu_catalog_service.list_catalog(scope_a)}
    ids_b = {row["id"] for row in menu_catalog_service.list_catalog(scope_b)}
    assert "MCD001" in ids_a
    assert "MCD001" not in ids_b
    assert all(not item_id.startswith("MCD") for item_id in ids_b)


def test_create_assigns_system_id_and_retire_hides_from_active(catalog):
    _, menu_catalog_service, scope = catalog
    created = menu_catalog_service.create_item(
        scope,
        {"name": "新品薯條", "category": "點心", "price": 40, "description": "熱騰騰"},
    )
    assert created["id"].startswith("itm_")
    assert created["name"] == "新品薯條"

    menu_catalog_service.retire_item(scope, created["id"])
    active_ids = {row["id"] for row in menu_catalog_service.list_catalog(scope, include_retired=False)}
    assert created["id"] not in active_ids
    all_ids = {row["id"] for row in menu_catalog_service.list_catalog(scope, include_retired=True)}
    assert created["id"] in all_ids

    restored = menu_catalog_service.restore_item(scope, created["id"])
    assert restored["retired"] is False
    active_ids = {row["id"] for row in menu_catalog_service.list_catalog(scope, include_retired=False)}
    assert created["id"] in active_ids


def test_upload_image_normalizes_and_sets_object_ref(catalog):
    _, menu_catalog_service, scope = catalog
    item = menu_catalog_service.create_item(
        scope,
        {"name": "有圖漢堡", "category": "超值全餐", "price": 70, "description": ""},
    )
    # 1000x500 solid image → longest edge 832
    import cv2

    canvas = np.zeros((500, 1000, 3), dtype=np.uint8)
    canvas[:] = (20, 120, 200)
    ok, encoded = cv2.imencode(".png", canvas)
    assert ok
    raw = encoded.tobytes()
    assert len(raw) < 5 * 1024 * 1024

    updated = menu_catalog_service.upload_item_image(
        scope,
        item["id"],
        data=raw,
        content_type="image/png",
        filename="big.png",
    )
    assert updated["image"].startswith("/api/menu/items/")
    assert str(updated.get("image_ref") or "").startswith("object:")
    data, ctype = menu_catalog_service.load_item_image_bytes(scope, item["id"])
    assert ctype == "image/jpeg"
    arr = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert decoded is not None
    h, w = decoded.shape[:2]
    assert max(h, w) <= 832


def test_checkout_rejects_sold_out_and_retired(catalog, tmp_path, monkeypatch):
    menu_repository, menu_catalog_service, scope = catalog
    menu_catalog_service.ensure_seeded(scope)

    from repositories import availability_repository
    from services import availability_service, checkout_pricing_service

    importlib.reload(availability_repository)
    monkeypatch.setattr(
        availability_repository,
        "AVAILABILITY_PATH",
        str(tmp_path / "availability.json"),
    )
    availability_repository.save_availability_scoped(
        {"sold_out_item_ids": ["MCD001"], "low_stock_item_ids": [], "store_disabled_item_ids": []},
        scope,
    )
    with pytest.raises(checkout_pricing_service.CartValidationError) as sold_out:
        checkout_pricing_service.price_checkout_cart(
            [{"id": "MCD001", "quantity": 1}],
            None,
            is_member=False,
            scope=scope,
        )
    assert sold_out.value.code == "item_sold_out"

    menu_catalog_service.retire_item(scope, "MCD900")
    with pytest.raises(checkout_pricing_service.CartValidationError) as retired:
        checkout_pricing_service.price_checkout_cart(
            [{"id": "MCD900", "quantity": 1}],
            None,
            is_member=False,
            scope=scope,
        )
    assert retired.value.code == "unknown_item"
