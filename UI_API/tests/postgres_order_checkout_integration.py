"""PostgreSQL integration for transactional Order checkout hardening."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _priced_cart() -> dict:
    return {
        "cart_ids": ["meal"],
        "cart_items": [
            {
                "id": "meal",
                "name": "Historical Meal",
                "category": "main",
                "quantity": 2,
                "base_unit_price": 120,
                "option_unit_total": 10,
                "discount_unit_total": 20,
                "final_unit_price": 110,
                "price": 110,
                "options": [{"id": "cheese", "name": "Cheese", "price": 10}],
                "promotion_snapshot": {
                    "promotion_ref": "launch-20",
                    "title": "Launch",
                    "discount_unit_total": 20,
                },
            }
        ],
        "subtotal": 240,
        "option_total": 20,
        "discount_total": 40,
        "tax_total": 0,
        "total": 220,
        "currency": "TWD",
        "calculation_version": "checkout-v1",
    }


def test_order_checkout_is_atomic_idempotent_and_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg
    from psycopg.rows import dict_row

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE, CommercialScope
    from models.order import InvalidOrderTransitionError, OrderStatus
    from repositories import checkout_order_repository, postgres_utils
    from services import observability_service
    from repositories.checkout_order_repository import checkout_request_fingerprint

    base_url = postgres_utils.database_url()
    schema = "order_checkout_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    migrations = postgres_utils.migration_files()
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgres")
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations[:6])
    postgres_utils.init_schema()

    legacy_member_id = uuid4()
    with psycopg.connect(scoped_url) as conn:
        conn.execute(
            "INSERT INTO members (id, phone, nickname, tenant_id) VALUES (%s, %s, %s, %s)",
            (legacy_member_id, "0912345678", "Legacy", LEGACY_DEFAULT_SCOPE.tenant_id),
        )
        conn.execute(
            """INSERT INTO member_orders (
                   member_id, phone, tenant_id, store_id, origin_device_id, total
               ) VALUES (%s, %s, %s, %s, %s, 99)""",
            (
                legacy_member_id,
                "0912345678",
                LEGACY_DEFAULT_SCOPE.tenant_id,
                LEGACY_DEFAULT_SCOPE.store_id,
                LEGACY_DEFAULT_SCOPE.device_id,
            ),
        )
        conn.commit()

    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations)
    postgres_utils.init_schema()
    priced = _priced_cart()
    fingerprint = checkout_request_fingerprint("checkout-session", priced)
    correlation_token = observability_service.bind_correlation_context(
        request_id="req_order_integration", trace_id="trace_order_integration"
    )
    try:
        created = checkout_order_repository.create_checkout_order_scoped(
            LEGACY_DEFAULT_SCOPE, "checkout-session", "checkout-key", fingerprint, priced
        )
    finally:
        observability_service.reset_correlation_context(correlation_token)
    replayed = checkout_order_repository.create_checkout_order_scoped(
        LEGACY_DEFAULT_SCOPE, "checkout-session", "checkout-key", fingerprint, priced
    )
    assert created["order_id"] == replayed["order_id"]
    assert created["replayed"] is False
    assert replayed["replayed"] is True
    assert created["status"] == "confirmed"
    assert created["total"] == 220

    with pytest.raises(checkout_order_repository.CheckoutIdempotencyConflictError):
        checkout_order_repository.create_checkout_order_scoped(
            LEGACY_DEFAULT_SCOPE, "checkout-session", "checkout-key", "f" * 64, priced
        )

    concurrent_key = "concurrent-key"
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(
            pool.map(
                lambda _index: checkout_order_repository.create_checkout_order_scoped(
                    LEGACY_DEFAULT_SCOPE,
                    "checkout-session",
                    concurrent_key,
                    fingerprint,
                    priced,
                ),
                range(2),
            )
        )
    assert len({row["order_id"] for row in concurrent}) == 1

    broken = _priced_cart()
    broken["cart_items"][0]["quantity"] = 0
    with pytest.raises(psycopg.errors.CheckViolation):
        checkout_order_repository.create_checkout_order_scoped(
            LEGACY_DEFAULT_SCOPE,
            "checkout-session",
            "rollback-key",
            checkout_request_fingerprint("checkout-session", broken),
            broken,
        )

    order_id = UUID(created["order_id"])
    with pytest.raises(InvalidOrderTransitionError):
        checkout_order_repository.transition_order_scoped(order_id, OrderStatus.COMPLETED, LEGACY_DEFAULT_SCOPE)
    checkout_order_repository.transition_order_scoped(order_id, OrderStatus.CANCEL_PENDING, LEGACY_DEFAULT_SCOPE)
    cancelled = checkout_order_repository.transition_order_scoped(order_id, OrderStatus.CANCELLED, LEGACY_DEFAULT_SCOPE)
    assert cancelled["status"] == "cancelled"

    tenant_b = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    store_b = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    device_b = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
    with psycopg.connect(scoped_url) as conn:
        conn.execute(
            "INSERT INTO tenants (id, code, name, status) VALUES (%s, 'order-b', 'Order B', 'active')",
            (tenant_b,),
        )
        conn.execute(
            """INSERT INTO stores (id, tenant_id, code, name, timezone, status)
               VALUES (%s, %s, 'order-b', 'Order B', 'Asia/Taipei', 'active')""",
            (store_b, tenant_b),
        )
        conn.execute(
            """INSERT INTO devices (id, tenant_id, store_id, code, name, status)
               VALUES (%s, %s, %s, 'order-b', 'Order B', 'active')""",
            (device_b, tenant_b, store_b),
        )
        conn.commit()
    scope_b = CommercialScope(tenant_b, store_b, device_b)
    tenant_b_order = checkout_order_repository.create_checkout_order_scoped(
        scope_b, "checkout-session", "checkout-key", fingerprint, priced
    )
    assert tenant_b_order["order_id"] != created["order_id"]
    default_orders, default_total = checkout_order_repository.list_orders_scoped(LEGACY_DEFAULT_SCOPE)
    tenant_b_orders, tenant_b_total = checkout_order_repository.list_orders_scoped(scope_b)
    assert default_total == 2
    assert tenant_b_total == 1
    assert {row["order_id"] for row in default_orders}.isdisjoint({row["order_id"] for row in tenant_b_orders})

    priced["cart_items"][0]["name"] = "Changed Later"
    with psycopg.connect(scoped_url, row_factory=dict_row) as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM member_orders").fetchone()["count"] == 1
        snapshot = conn.execute("SELECT product_name FROM order_items WHERE order_id = %s", (order_id,)).fetchone()
        assert snapshot["product_name"] == "Historical Meal"
        assert (
            conn.execute("SELECT COUNT(*) AS count FROM orders WHERE idempotency_key = 'rollback-key'").fetchone()[
                "count"
            ]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) AS count FROM orders WHERE idempotency_key IN ('checkout-key', 'concurrent-key')"
            ).fetchone()["count"]
            == 0
        )
        assert (
            conn.execute("SELECT COUNT(*) AS count FROM order_outbox WHERE aggregate_id = %s", (order_id,)).fetchone()[
                "count"
            ]
            == 2
        )
        confirmed_payload = conn.execute(
            "SELECT payload FROM order_outbox WHERE aggregate_id = %s AND event_type = 'order_confirmed'",
            (order_id,),
        ).fetchone()["payload"]
        assert confirmed_payload["trace_id"] == "trace_order_integration"
        assert "session_id" not in confirmed_payload
        assert (
            conn.execute("SELECT checkout_success FROM order_outcomes WHERE order_id = %s", (order_id,)).fetchone()[
                "checkout_success"
            ]
            is True
        )

    postgres_utils.validate_migration_plan(postgres_utils.get_migration_plan(), require_clean=True)


def test_checkout_outbox_relogin_exposes_member_order_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the production confirmation/outbox consumer across a fresh login."""
    import psycopg

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from modules.cart import CartModule, PostgresCartStore
    from modules.checkout_confirmation import CheckoutConfirmationModule
    from modules.checkout_confirmation import runtime as checkout_runtime
    from modules.checkout_confirmation.postgres_store import PostgresCheckoutStore
    from repositories import postgres_utils
    from services import member_service

    base_url = postgres_utils.database_url()
    schema = "member_history_checkout_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        try:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.execute(f'CREATE SCHEMA "{schema}"')
        except psycopg.errors.InsufficientPrivilege:
            pytest.skip("PostgreSQL integration role cannot create an isolated schema")
    scoped_url = _schema_url(base_url, schema)
    migrations = postgres_utils.migration_files()
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgresql")
    monkeypatch.setattr(postgres_utils, "migration_files", lambda: migrations)
    postgres_utils.init_schema()
    member_service._session_member.clear()

    phone = "0912345678"
    session_id = "checkout-history-session"
    registered = member_service.register(session_id, phone, "歷史測試會員", scope=LEGACY_DEFAULT_SCOPE)
    assert registered["ok"] is True

    cart = CartModule(PostgresCartStore())
    cart.replace(
        scope=LEGACY_DEFAULT_SCOPE,
        session_id=session_id,
        expected_revision=0,
        lines=[{"item_id": "meal", "quantity": 2, "options": []}],
    )

    class Pricing:
        @staticmethod
        def price(*, scope, session_id, lines):
            return {"subtotal": 220, "option_total": 0, "discount_total": 0, "tax_total": 0, "total": 220}

    class Fulfillment:
        @staticmethod
        def validate(*, scope, lines):
            return []

    checkout = CheckoutConfirmationModule(
        store=PostgresCheckoutStore(),
        cart=cart,
        pricing=Pricing(),
        fulfillment=Fulfillment(),
    )
    quote = checkout.prepare(scope=LEGACY_DEFAULT_SCOPE, session_id=session_id)
    confirmed = checkout.confirm(
        scope=LEGACY_DEFAULT_SCOPE,
        quote_id=quote["quote_id"],
        idempotency_key="history-confirmation",
    )
    assert confirmed["type"] == "confirmed"

    monkeypatch.setattr(checkout_runtime, "default_module", lambda: checkout)
    dispatched = checkout_runtime.dispatch_outbox()
    assert len(dispatched["published_event_ids"]) == 1
    assert dispatched["failed_event_ids"] == []

    relogin = member_service.login("relogin-session", phone, scope=LEGACY_DEFAULT_SCOPE)
    assert relogin["found"] is True
    history = relogin["member"]["history"]
    assert len(history) == 1
    assert history[0]["total"] == 220
    assert history[0]["items"] == [{"id": "meal", "name": "meal", "price": 0, "count": 2}]

    with psycopg.connect(scoped_url) as conn:
        row = conn.execute(
            "SELECT origin_device_id, published_at FROM checkout_outbox WHERE event_type = 'OrderConfirmed'"
        ).fetchone()
        assert row[0] == LEGACY_DEFAULT_SCOPE.device_id
        assert row[1] is not None
