"""PostgreSQL evidence for Recommendation effectiveness from durable touch facts."""

import os
import uuid

import pytest

from capabilities.recommendation_analytics import build_effectiveness_report, record_touch
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.analytics import _pipeline as analytics_pipeline_service
from modules.checkout_confirmation.adapters.orders import (
    checkout_request_fingerprint,
    create_checkout_order_scoped,
    list_order_touch_attributions_scoped,
    upsert_order_touch_attributions_scoped,
)
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="effectiveness evidence requires PostgreSQL touch and order facts",
    )
)


def test_effectiveness_report_reads_postgres_touch_and_attribution_facts():
    suffix = uuid.uuid4().hex
    session_id = f"effectiveness-{suffix}"
    impression_id = f"impression-{suffix}"
    impression_event_id = f"touch-impression-{suffix}"
    click_event_id = f"touch-click-{suffix}"
    priced_cart = {
        "currency": "TWD",
        "calculation_version": "checkout-v1",
        "subtotal": 120,
        "option_total": 0,
        "discount_total": 0,
        "tax_total": 0,
        "total": 120,
        "cart_items": [
            {
                "id": "effectiveness-item",
                "name": "Effectiveness item",
                "category": "test",
                "quantity": 1,
                "base_unit_price": 120,
                "option_unit_total": 0,
                "discount_unit_total": 0,
                "final_unit_price": 120,
                "options": [],
            }
        ],
    }
    order = create_checkout_order_scoped(
        LEGACY_DEFAULT_SCOPE,
        session_id,
        f"effectiveness-{suffix}",
        checkout_request_fingerprint(session_id, priced_cart),
        priced_cart,
    )
    order_id = order["order_id"]
    order_item_id = order["items"][0]["order_item_id"]

    try:
        for event_id, event_type in (
            (impression_event_id, "impression"),
            (click_event_id, "click"),
        ):
            receipt = record_touch(
                {
                    "event_id": event_id,
                    "event_type": event_type,
                    "decision_id": f"missing-decision-{suffix}",
                    "impression_id": impression_id,
                    "placement": "menu",
                    "item_id": "effectiveness-item",
                    "session_id": session_id,
                    "strategy_version": "effectiveness-v1",
                    "variant_id": "control",
                    "audience": "guest",
                },
                LEGACY_DEFAULT_SCOPE,
            )
            assert receipt.accepted is True

        assert (
            upsert_order_touch_attributions_scoped(
                LEGACY_DEFAULT_SCOPE,
                [
                    {
                        "order_id": order_id,
                        "order_item_id": order_item_id,
                        "impression_id": impression_id,
                        "attribution_type": "direct",
                        "attributed_revenue": 120,
                        "attributed_discount": 0,
                        "status": "confirmed",
                    }
                ],
            )
            == 1
        )

        events = analytics_pipeline_service.list_events(
            tenant_id=LEGACY_DEFAULT_SCOPE.tenant_id,
            store_id=LEGACY_DEFAULT_SCOPE.store_id,
        )
        attributions = list_order_touch_attributions_scoped(LEGACY_DEFAULT_SCOPE)
        report = build_effectiveness_report(events, attributions, filters={"placement": "menu"})

        assert report.impressions == 1
        assert report.clicks == 1
        assert report.purchases == 1
        assert report.attributed_revenue == 120
        assert report.breakdowns == [{"variant_id": "control", "impressions": 1, "clicks": 1, "add_to_carts": 0}]
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM orders WHERE id = %s", (order_id,))
            cur.execute(
                "DELETE FROM analytics_event_log WHERE event_id IN (%s, %s)",
                (impression_event_id, click_event_id),
            )
            cur.execute(
                "DELETE FROM commercial_touch_events WHERE event_id IN (%s, %s)",
                (impression_event_id, click_event_id),
            )
            conn.commit()
