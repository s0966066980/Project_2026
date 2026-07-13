"""Transactional PostgreSQL Order aggregate and idempotency boundary."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

from models.commercial_scope import CommercialScope
from models.order import OrderStatus, transition_order_status
from repositories import postgres_utils


class CheckoutIdempotencyConflictError(ValueError):
    """An idempotency key was reused for a different safe request fingerprint."""


def _jsonb(value: object):
    try:
        from psycopg.types.json import Jsonb
    except Exception as exc:
        raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
    return Jsonb(value)


def _validated_key(value: str) -> str:
    key = str(value or "").strip()
    if not key or len(key) > 200:
        raise ValueError("A bounded Idempotency-Key is required")
    return hashlib.sha256(key.encode()).hexdigest()


def _order_result(cur, order_id: UUID, *, replayed: bool) -> dict:
    cur.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
    order = cur.fetchone()
    if order is None:
        raise postgres_utils.PostgresOperationError("Order result is unavailable")
    cur.execute("SELECT * FROM order_items WHERE order_id = %s ORDER BY id", (order_id,))
    items = cur.fetchall()
    return {
        "order_id": str(order["id"]),
        "status": str(order["status"]),
        "currency": str(order["currency"]),
        "calculation_version": str(order["calculation_version"]),
        "subtotal": int(order["subtotal"]),
        "option_total": int(order["option_total"]),
        "discount_total": int(order["discount_total"]),
        "tax_total": int(order["tax_total"]),
        "total": int(order["total"]),
        "items": [
            {
                "item_id": str(item["item_id"]),
                "product_name": str(item["product_name"]),
                "quantity": int(item["quantity"]),
                "base_unit_price": int(item["base_unit_price"]),
                "option_unit_total": int(item["option_unit_total"]),
                "discount_unit_total": int(item["discount_unit_total"]),
                "final_unit_price": int(item["final_unit_price"]),
                "options": item["options_snapshot"],
            }
            for item in items
        ],
        "replayed": replayed,
    }


def create_checkout_order_scoped(
    scope: CommercialScope,
    session_id: str,
    idempotency_key: str,
    request_fingerprint: str,
    priced_cart: dict,
) -> dict:
    """Atomically create one confirmed Order, snapshots, promotion usage, and outbox event."""

    if not postgres_utils.use_postgres():
        raise ValueError("Transactional checkout orders require PostgreSQL storage")
    key = _validated_key(idempotency_key)
    fingerprint = str(request_fingerprint or "").strip()
    if len(fingerprint) != 64:
        raise ValueError("A SHA-256 checkout request fingerprint is required")
    order_id = uuid4()
    outbox_id = uuid4()
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT member_id FROM member_sessions
            WHERE session_id = %s AND tenant_id = %s AND store_id = %s
            """,
            (session_id, scope.tenant_id, scope.store_id),
        )
        session_member = cur.fetchone()
        member_id = session_member["member_id"] if session_member else None
        cur.execute(
            """
            INSERT INTO orders (
                id, tenant_id, store_id, origin_device_id, member_id, session_id,
                status, idempotency_key, request_fingerprint, currency, calculation_version,
                subtotal, option_total, discount_total, tax_total, total, confirmed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                'confirmed', %s, %s, %s, %s,
                %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (tenant_id, store_id, idempotency_key) DO NOTHING
            RETURNING id
            """,
            (
                order_id,
                scope.tenant_id,
                scope.store_id,
                scope.device_id,
                member_id,
                str(session_id or ""),
                key,
                fingerprint,
                str(priced_cart.get("currency") or "TWD"),
                str(priced_cart.get("calculation_version") or "checkout-v1"),
                int(priced_cart.get("subtotal") or 0),
                int(priced_cart.get("option_total") or 0),
                int(priced_cart.get("discount_total") or 0),
                int(priced_cart.get("tax_total") or 0),
                int(priced_cart.get("total") or 0),
            ),
        )
        inserted = cur.fetchone()
        if inserted is None:
            cur.execute(
                """SELECT id, request_fingerprint FROM orders
                   WHERE tenant_id = %s AND store_id = %s AND idempotency_key = %s""",
                (scope.tenant_id, scope.store_id, key),
            )
            existing = cur.fetchone()
            if existing is None or existing["request_fingerprint"] != fingerprint:
                raise CheckoutIdempotencyConflictError("Idempotency key was used for another request")
            conn.commit()
            return _order_result(cur, existing["id"], replayed=True)

        for item in priced_cart.get("cart_items") or []:
            cur.execute(
                """
                INSERT INTO order_items (
                    order_id, item_id, product_name, category, quantity,
                    base_unit_price, option_unit_total, discount_unit_total,
                    final_unit_price, options_snapshot
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    order_id,
                    str(item.get("id") or ""),
                    str(item.get("name") or item.get("id") or ""),
                    str(item.get("category") or ""),
                    int(item.get("quantity") or 0),
                    int(item.get("base_unit_price") or 0),
                    int(item.get("option_unit_total") or 0),
                    int(item.get("discount_unit_total") or 0),
                    int(item.get("final_unit_price") or 0),
                    _jsonb(item.get("options") or []),
                ),
            )
            order_item_id = cur.fetchone()["id"]
            promotion = item.get("promotion_snapshot")
            if isinstance(promotion, dict) and promotion.get("promotion_ref"):
                cur.execute(
                    """
                    INSERT INTO order_promotion_usages (
                        order_id, order_item_id, promotion_ref, promotion_title,
                        discount_amount, promotion_snapshot
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        order_id,
                        order_item_id,
                        str(promotion.get("promotion_ref")),
                        str(promotion.get("title") or ""),
                        int(promotion.get("discount_unit_total") or 0) * int(item.get("quantity") or 0),
                        _jsonb(promotion),
                    ),
                )
        cur.execute(
            """
            INSERT INTO order_outcomes (order_id, checkout_success, metadata)
            VALUES (%s, TRUE, %s)
            """,
            (order_id, _jsonb({"source": "checkout"})),
        )
        cur.execute(
            """
            INSERT INTO order_outbox (id, tenant_id, store_id, aggregate_id, event_type, payload)
            VALUES (%s, %s, %s, %s, 'order_confirmed', %s)
            """,
            (
                outbox_id,
                scope.tenant_id,
                scope.store_id,
                order_id,
                _jsonb(
                    {
                        "order_id": str(order_id),
                        "status": OrderStatus.CONFIRMED.value,
                        "currency": str(priced_cart.get("currency") or "TWD"),
                        "total": int(priced_cart.get("total") or 0),
                    }
                ),
            ),
        )
        result = _order_result(cur, order_id, replayed=False)
        conn.commit()
    return result


def transition_order_scoped(order_id: UUID, target: OrderStatus, scope: CommercialScope) -> dict:
    """Apply the domain state machine and emit terminal outbox events in one transaction."""

    event_by_status = {
        OrderStatus.COMPLETED: "order_completed",
        OrderStatus.CANCELLED: "order_cancelled",
    }
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT status FROM orders
               WHERE id = %s AND tenant_id = %s AND store_id = %s AND origin_device_id = %s
               FOR UPDATE""",
            (order_id, scope.tenant_id, scope.store_id, scope.device_id),
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError("Order was not found in the commercial scope")
        current = OrderStatus(row["status"])
        transition_order_status(current, target)
        timestamp_column = {
            OrderStatus.COMPLETED: "completed_at",
            OrderStatus.CANCELLED: "cancelled_at",
        }.get(target)
        if timestamp_column:
            cur.execute(
                f"UPDATE orders SET status = %s, updated_at = NOW(), {timestamp_column} = NOW() WHERE id = %s",
                (target.value, order_id),
            )
        else:
            cur.execute("UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s", (target.value, order_id))
        event_type = event_by_status.get(target)
        if event_type:
            cur.execute(
                """
                INSERT INTO order_outbox (id, tenant_id, store_id, aggregate_id, event_type, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (aggregate_id, event_type) DO NOTHING
                """,
                (
                    uuid4(),
                    scope.tenant_id,
                    scope.store_id,
                    order_id,
                    event_type,
                    _jsonb({"order_id": str(order_id), "status": target.value}),
                ),
            )
        result = _order_result(cur, order_id, replayed=False)
        conn.commit()
    return result
