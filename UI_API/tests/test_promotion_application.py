from datetime import datetime, timezone
from uuid import UUID


def _context(**overrides):
    from modules.promotion.contracts import PromotionContext

    values = {
        "now": datetime(2026, 7, 14, 4, 0, tzinfo=timezone.utc),
        "is_member": False,
        "item_id": "MCD012",
        "category": "點心",
        "cart_item_ids": frozenset({"MCD001", "MCD012"}),
        "placement": "recommendation",
    }
    values.update(overrides)
    return PromotionContext(**values)


def test_evaluate_promotion_accepts_only_active_eligible_context():
    from modules.promotion.application import evaluate_promotion

    promotion = {
        "offer_id": "meal-fries",
        "status": "active",
        "enabled": True,
        "starts_at": "2026-07-14",
        "ends_at": "2026-07-14",
        "timezone": "Asia/Taipei",
        "item_ids": ["MCD012"],
        "required_cart_item_ids": ["MCD001"],
    }

    assert evaluate_promotion(promotion, _context()).eligible is True
    assert evaluate_promotion({**promotion, "enabled": False}, _context()).code == "promotion_disabled"
    assert evaluate_promotion(promotion, _context(is_member=False, item_id="MCD030")).code == "target_mismatch"


def test_evaluate_promotion_requires_every_cart_prerequisite():
    from modules.promotion.application import evaluate_promotion

    promotion = {
        "offer_id": "complete-combo",
        "status": "active",
        "enabled": True,
        "categories": ["飲料"],
        "required_cart_item_ids": ["MCD001", "MCD012"],
    }

    partial = _context(
        item_id="MCD030",
        category="飲料",
        cart_item_ids=frozenset({"MCD001", "MCD030"}),
    )
    complete = _context(
        item_id="MCD030",
        category="飲料",
        cart_item_ids=frozenset({"MCD001", "MCD012", "MCD030"}),
    )

    assert evaluate_promotion(promotion, partial).code == "requirements_not_met"
    assert evaluate_promotion(promotion, complete).eligible is True


def test_evaluate_promotion_fails_closed_for_member_scope_and_placement():
    from models.commercial_scope import CommercialScope
    from modules.promotion.application import evaluate_promotion

    scope = CommercialScope(
        tenant_id=UUID("00000000-0000-4000-8000-000000000010"),
        store_id=UUID("00000000-0000-4000-8000-000000000020"),
    )
    promotion = {
        "offer_id": "member-fries",
        "status": "active",
        "enabled": True,
        "member_only": True,
        "tenant_id": str(scope.tenant_id),
        "store_id": str(scope.store_id),
        "placements": ["recommendation", "kiosk_cart_banner"],
        "item_ids": ["MCD012"],
    }

    assert evaluate_promotion(promotion, _context(scope=scope)).code == "member_required"
    assert evaluate_promotion(
        promotion,
        _context(scope=scope, is_member=True, placement="menu"),
    ).code == "placement_mismatch"
    assert evaluate_promotion(
        promotion,
        _context(scope=None, is_member=True),
    ).code == "scope_mismatch"


def test_quote_promotion_returns_authoritative_effective_price():
    from modules.promotion.application import quote_promotion

    quote = quote_promotion(
        {
            "offer_id": "meal-fries",
            "title": "套餐加購薯條",
            "status": "active",
            "enabled": True,
            "item_ids": ["MCD012"],
            "pricing": {"promotion_price": 30},
        },
        _context(),
        base_price=45,
    )

    assert quote.eligible is True
    assert quote.effective_price == 30
    assert quote.discount == 15
    assert quote.promotion_ref == "meal-fries"


def test_project_item_price_distinguishes_conditional_benefit():
    from modules.promotion.application import project_item_price

    promotion = {
        "offer_id": "meal-fries",
        "title": "套餐加購薯條",
        "status": "active",
        "enabled": True,
        "item_ids": ["MCD012"],
        "required_cart_item_ids": ["MCD001"],
        "promotion_price": 30,
    }

    conditional = project_item_price(
        [promotion],
        _context(cart_item_ids=frozenset({"MCD012"})),
        base_price=45,
    )
    applied = project_item_price([promotion], _context(), base_price=45)

    assert conditional.conditional is True
    assert conditional.effective_price == 45
    assert conditional.required_cart_item_ids == ("MCD001",)
    assert applied.conditional is False
    assert applied.effective_price == 30
