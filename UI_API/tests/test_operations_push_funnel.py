"""The operations overview's push half, read from facts that have writers.

Both numbers on this panel used to come from `session_logs`. Its only writer,
`record_final_checkout`, had no callers anywhere in the application, so the
table was permanently empty and the success rate and the order detail table
were structurally zero whatever the store did. Neither was a rendering bug.

They now read the analytics touch log and the confirmed-order store. These are
PostgreSQL checks because both are PostgreSQL tables and the readers return
empty on SQLite by design.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.operations_overview.module import PushFunnel, PushFunnelModule
from repositories import postgres_utils

pytestmark = [pytest.mark.unit, pytest.mark.contract]

SCOPE = LEGACY_DEFAULT_SCOPE


class _Store:
    """A funnel store that answers exactly what a test says."""

    def __init__(self, *, touches=None, orders=0, attributed=0, rows=None):
        self.touches = touches or {}
        self.orders = orders
        self.attributed = attributed
        self.rows = rows or []

    def count_touches(self, *, scope, since, event_type):
        return int(self.touches.get(event_type, 0))

    def count_confirmed_orders(self, *, scope, since):
        return self.orders

    def count_attributed_orders(self, *, scope, since):
        return self.attributed

    def recent_confirmed_orders(self, *, scope, limit):
        return self.rows[:limit]


def _module(**kwargs) -> PushFunnelModule:
    return PushFunnelModule(store=_Store(**kwargs))


def test_the_success_rate_is_attributed_orders_over_impressions():
    """What was shown, and how much of it was paid for."""

    funnel = _module(touches={"impression": 200, "add_to_cart": 40}, orders=25, attributed=10).funnel(
        scope=SCOPE, since=""
    )

    assert funnel.success_rate == 0.05
    assert funnel.as_dict()["success_sessions"] == 10
    assert funnel.as_dict()["failure_sessions"] == 190


def test_no_impressions_is_a_zero_rate_and_not_a_crash():
    """An empty store divides by nothing; the panel still has to render."""

    funnel = _module(touches={}, orders=0, attributed=0).funnel(scope=SCOPE, since="")

    assert funnel.success_rate == 0.0
    assert funnel.as_dict()["failure_sessions"] == 0


def test_more_attributed_orders_than_impressions_never_reports_over_one():
    """Attribution can outrun a filtered impression window; a rate above 100% is a bug on screen."""

    funnel = PushFunnel(impressions=5, add_to_carts=9, orders=9, attributed_orders=9)

    assert funnel.as_dict()["failure_sessions"] == 0, "a negative failure count reached the screen"


def test_the_panel_reports_no_cumulative_score():
    """The old score lived in the session log; inventing one from the funnel would mean nothing."""

    assert "cumulative_score" not in _module(orders=3).funnel(scope=SCOPE, since="").as_dict()


def test_the_detail_rows_are_confirmed_orders():
    rows = [{"order_id": "o1"}, {"order_id": "o2"}]

    assert _module(rows=rows).sessions(scope=SCOPE, limit=10) == rows


def test_the_detail_rows_are_bounded():
    rows = [{"order_id": str(index)} for index in range(50)]

    assert len(_module(rows=rows).sessions(scope=SCOPE, limit=5)) == 5


def test_every_number_states_what_it_counts():
    """A rate with no stated denominator is read as whatever the reader assumes."""

    definitions = _module(orders=1).funnel(scope=SCOPE, since="").as_dict()["definitions"]

    assert definitions["success_rate"]
    assert definitions["sessions"]


# --- against the real stores -------------------------------------------------


def _on_postgres() -> bool:
    return str(os.environ.get("DATABASE_BACKEND", "")).strip() == "postgresql" and postgres_utils.use_postgres()


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="both stores are PostgreSQL tables")
def test_the_detail_table_reads_the_table_the_writer_uses():
    """`list_orders_scoped` reads `orders`; confirmations land in `confirmed_orders`.

    Nothing in this runtime writes `orders`, which is why the detail table was
    empty while real orders sat in the database. This asserts the reader is
    pointed at the table with the rows in it.
    """

    from modules.checkout_confirmation.adapters import orders as checkout_orders

    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS rows FROM confirmed_orders WHERE tenant_id = %s AND store_id = %s",
            (SCOPE.tenant_id, SCOPE.store_id),
        )
        confirmed = int(cur.fetchone()["rows"])

    listed = checkout_orders.list_confirmed_orders_scoped(SCOPE, limit=500)

    assert len(listed) == min(confirmed, 500)
    if listed:
        assert listed[0]["order_id"], "an order came back without its identity"
        assert "total" in listed[0]


@pytest.mark.postgres
@pytest.mark.integration
@pytest.mark.skipif(not _on_postgres(), reason="both stores are PostgreSQL tables")
def test_a_confirmed_order_appears_in_the_detail_rows():
    from modules.checkout_confirmation.adapters import orders as checkout_orders

    order_id = uuid.uuid4()
    session_id = f"funnel-gate-{uuid.uuid4().hex[:10]}"
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO confirmed_orders
                (tenant_id, store_id, order_id, quote_id, session_id, status,
                 lines_json, pricing_json, created_at, pickup_number)
            VALUES (%s, %s, %s, %s, %s, 'payment_pending', %s, %s, %s, 0)
            """,
            (
                SCOPE.tenant_id,
                SCOPE.store_id,
                str(order_id),
                f"quote-{order_id}",
                session_id,
                '[{"item_id": "MCD001", "quantity": 2}]',
                '{"total": 240, "currency": "TWD"}',
                datetime.now(timezone.utc) + timedelta(seconds=1),
            ),
        )
        conn.commit()

    try:
        rows = checkout_orders.list_confirmed_orders_scoped(SCOPE, limit=10)
        mine = [row for row in rows if row["session_id"] == session_id]

        assert mine, "a confirmed order did not reach the detail rows"
        assert mine[0]["total"] == 240
        assert mine[0]["items"] == [{"item_id": "MCD001", "quantity": 2}]
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM confirmed_orders WHERE order_id = %s", (str(order_id),))
            conn.commit()
