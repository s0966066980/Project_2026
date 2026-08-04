def test_order_item_attribution_uses_snapshot_and_one_touch():
    from modules.analytics.application import build_order_attributions

    order = {
        "order_id": "order-1",
        "status": "confirmed",
        "items": [{
            "order_item_id": 10,
            "item_id": "MCD012",
            "quantity": 2,
            "final_unit_price": 30,
            "discount_unit_total": 15,
        }],
    }
    touches = [
        {
            "event_type": "recommendation_shown",
            "item_id": "MCD012",
            "recommendation_id": "decision-old",
            "timestamp": "2026-07-14T10:00:00+00:00",
        },
        {
            "event_type": "recommendation_added_to_cart",
            "item_id": "MCD012",
            "recommendation_id": "decision-direct",
            "impression_id": "impression-direct",
            "timestamp": "2026-07-14T10:01:00+00:00",
        },
    ]

    rows = build_order_attributions(order, touches)

    assert rows == [{
        "order_id": "order-1",
        "order_item_id": 10,
        "item_id": "MCD012",
        "decision_id": "decision-direct",
        "impression_id": "impression-direct",
        "attribution_type": "direct",
        "attributed_revenue": 60,
        "attributed_discount": 30,
        "status": "provisional",
    }]


def test_cancelled_order_attribution_is_reversed():
    from modules.analytics.application import build_order_attributions

    rows = build_order_attributions(
        {
            "order_id": "order-2",
            "status": "cancelled",
            "items": [{
                "order_item_id": 11,
                "item_id": "MCD001",
                "quantity": 1,
                "final_unit_price": 100,
                "discount_unit_total": 20,
            }],
        },
        [{
            "event_type": "recommendation_shown",
            "item_id": "MCD001",
            "recommendation_id": "decision-view",
        }],
    )

    assert rows[0]["attribution_type"] == "view_through"
    assert rows[0]["status"] == "reversed"


def test_checkout_snapshot_is_a_direct_touch():
    from modules.analytics.application import build_order_attributions

    rows = build_order_attributions(
        {
            "order_id": "order-3",
            "status": "pending",
            "items": [{
                "order_item_id": 12,
                "item_id": "MCD003",
                "quantity": 1,
                "final_unit_price": 90,
                "discount_unit_total": 10,
            }],
        },
        [{
            "event_type": "recommendation_checked_out",
            "item_id": "MCD003",
            "recommendation_id": "decision-checkout",
        }],
    )

    assert rows[0]["attribution_type"] == "direct"
    assert rows[0]["decision_id"] == "decision-checkout"
