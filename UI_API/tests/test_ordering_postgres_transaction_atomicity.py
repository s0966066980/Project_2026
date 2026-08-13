"""PostgreSQL evidence for atomic Checkout confirmation writes."""

import os
import uuid

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.checkout_confirmation.adapters.orders import (
    checkout_request_fingerprint,
    create_checkout_order_scoped,
)
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="transactional checkout authority lives in PostgreSQL",
    )
)


def test_checkout_confirmation_rolls_back_order_items_and_outbox_together():
    session_id = f"atomicity-{uuid.uuid4().hex}"
    idempotency_key = f"atomicity-{uuid.uuid4().hex}"
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
                "id": "valid-item",
                "name": "Valid item",
                "category": "test",
                "quantity": 1,
                "base_unit_price": 120,
                "option_unit_total": 0,
                "discount_unit_total": 0,
                "final_unit_price": 120,
                "options": [],
            },
            {
                "id": "invalid-item",
                "name": "Invalid item",
                "category": "test",
                "quantity": 0,
                "base_unit_price": 1,
                "option_unit_total": 0,
                "discount_unit_total": 0,
                "final_unit_price": 1,
                "options": [],
            },
        ],
    }

    with pytest.raises(Exception):
        create_checkout_order_scoped(
            LEGACY_DEFAULT_SCOPE,
            session_id,
            idempotency_key,
            checkout_request_fingerprint(session_id, priced_cart),
            priced_cart,
        )

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS count FROM orders WHERE tenant_id = %s AND store_id = %s AND session_id = %s",
            (LEGACY_DEFAULT_SCOPE.tenant_id, LEGACY_DEFAULT_SCOPE.store_id, session_id),
        )
        assert int(cur.fetchone()["count"]) == 0
        cur.execute(
            """
            SELECT count(*) AS count
            FROM order_outbox outbox
            JOIN orders order_row ON order_row.id = outbox.aggregate_id
            WHERE order_row.tenant_id = %s AND order_row.store_id = %s AND order_row.session_id = %s
            """,
            (LEGACY_DEFAULT_SCOPE.tenant_id, LEGACY_DEFAULT_SCOPE.store_id, session_id),
        )
        assert int(cur.fetchone()["count"]) == 0
