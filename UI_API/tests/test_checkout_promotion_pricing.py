import json
from datetime import datetime, timezone

import pytest


MENU = [
    {"id": "MCD001", "name": "大麥克套餐", "price": 155, "category": "超值全餐"},
    {"id": "MCD012", "name": "薯條(中)", "price": 45, "category": "點心"},
    {"id": "MCD030", "name": "可口可樂(中)", "price": 35, "category": "飲料"},
]


def _configure_catalog_and_promotion(tmp_path, monkeypatch, promotion):
    from repositories import promotion_repository
    from services import checkout_pricing_service

    promotion_root = tmp_path / "promotions"
    promotion_root.mkdir()
    (promotion_root / f"{promotion['offer_id']}.json").write_text(
        json.dumps(promotion, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(promotion_repository, "promotions_root", lambda: promotion_root)
    monkeypatch.setattr(promotion_repository, "promotion_path", lambda offer_id: promotion_root / f"{offer_id}.json")
    monkeypatch.setattr(checkout_pricing_service.menu_repository, "get_menu", lambda: MENU)
    return checkout_pricing_service


def test_checkout_applies_eligible_fixed_price_and_records_snapshot(tmp_path, monkeypatch):
    checkout_pricing_service = _configure_catalog_and_promotion(tmp_path, monkeypatch, {
        "offer_id": "meal-fries",
        "title": "套餐加購薯條",
        "status": "active",
        "enabled": True,
        "item_ids": ["MCD012"],
        "required_cart_item_ids": ["MCD001"],
        "pricing": {"type": "add_on_fixed_price", "promotion_price": 30},
    })

    priced = checkout_pricing_service.price_checkout_cart(
        [
            {"id": "MCD001", "quantity": 1},
            {"id": "MCD012", "quantity": 2, "applied_offer_id": "meal-fries"},
        ],
        ["MCD001", "MCD012"],
        is_member=False,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    fries = next(item for item in priced["cart_items"] if item["id"] == "MCD012")
    assert priced["subtotal"] == 245
    assert priced["discount_total"] == 30
    assert priced["total"] == 215
    assert fries["final_unit_price"] == 30
    assert fries["promotion_snapshot"] == {
        "promotion_ref": "meal-fries",
        "title": "套餐加購薯條",
        "discount_unit_total": 15,
    }


def test_checkout_returns_same_best_price_without_client_offer_hint(tmp_path, monkeypatch):
    checkout_pricing_service = _configure_catalog_and_promotion(tmp_path, monkeypatch, {
        "offer_id": "meal-fries",
        "title": "套餐加購薯條",
        "status": "active",
        "enabled": True,
        "item_ids": ["MCD012"],
        "required_cart_item_ids": ["MCD001"],
        "promotion_price": 30,
    })
    cart = [
        {"id": "MCD001", "quantity": 1},
        {"id": "MCD012", "quantity": 1},
    ]

    without_hint = checkout_pricing_service.price_checkout_cart(
        cart,
        ["MCD001", "MCD012"],
        is_member=False,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    with_hint = checkout_pricing_service.price_checkout_cart(
        [cart[0], {**cart[1], "applied_offer_id": "meal-fries"}],
        ["MCD001", "MCD012"],
        is_member=False,
        now=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )

    assert without_hint["total"] == 185
    assert without_hint == with_hint


def test_checkout_requires_all_configured_prerequisite_items(tmp_path, monkeypatch):
    checkout_pricing_service = _configure_catalog_and_promotion(tmp_path, monkeypatch, {
        "offer_id": "complete-combo-drink",
        "title": "完整套餐加購飲料",
        "status": "active",
        "enabled": True,
        "item_ids": ["MCD030"],
        "required_cart_item_ids": ["MCD001", "MCD012"],
        "promotion_price": 20,
    })

    with pytest.raises(checkout_pricing_service.CartValidationError) as exc:
        checkout_pricing_service.price_checkout_cart(
            [
                {"id": "MCD001", "quantity": 1},
                {"id": "MCD030", "quantity": 1, "applied_offer_id": "complete-combo-drink"},
            ],
            ["MCD001", "MCD030"],
            is_member=False,
            now=datetime(2026, 7, 14, tzinfo=timezone.utc),
        )

    assert exc.value.code == "promotion_requirements_not_met"
