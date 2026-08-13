"""PostgreSQL cart writes must serialize stale-revision checks."""

import os
import threading
import uuid

import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.cart import CartError, PostgresCartStore
from repositories import postgres_utils

pytestmark = [pytest.mark.integration, pytest.mark.postgres, pytest.mark.contract]
pytestmark.append(
    pytest.mark.skipif(
        str(os.environ.get("DATABASE_BACKEND", "")).strip() != "postgresql" or not postgres_utils.use_postgres(),
        reason="cart concurrency authority lives in PostgreSQL",
    )
)


LINES = [{"item_id": "coffee", "quantity": 1, "options": [], "applied_offer_id": ""}]


def _race(session_id: str, *, expected_revision: int) -> list[str]:
    """Two writers submit the same expected revision at the same instant."""

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def replace_cart():
        store = PostgresCartStore()
        barrier.wait()
        try:
            store.replace(
                scope=LEGACY_DEFAULT_SCOPE,
                session_id=session_id,
                expected_revision=expected_revision,
                lines=LINES,
            )
            outcome = "committed"
        except CartError as exc:
            outcome = exc.code
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=replace_cart) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(outcomes)


def _purge(session_id: str) -> None:
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM ordering_carts WHERE tenant_id = %s AND store_id = %s AND session_id = %s",
            (LEGACY_DEFAULT_SCOPE.tenant_id, LEGACY_DEFAULT_SCOPE.store_id, session_id),
        )
        conn.commit()


def test_two_writers_creating_the_same_cart_produce_one_winner():
    """Both threads reach a cart that does not exist yet.

    What serializes this case is the unique index behind
    `INSERT ... ON CONFLICT DO NOTHING`: the second insert waits on the first
    transaction, so it reads revision 1 and is refused. Row locking is not what
    holds this line — see the test below for the case that needs it.
    """

    session_id = f"cart-create-{uuid.uuid4().hex}"
    try:
        assert _race(session_id, expected_revision=0) == ["cart_revision_conflict", "committed"]
        current = PostgresCartStore().get(scope=LEGACY_DEFAULT_SCOPE, session_id=session_id)
        assert current["revision"] == 1
        assert current["lines"] == LINES
    finally:
        _purge(session_id)


def test_two_writers_updating_an_existing_cart_produce_one_winner():
    """The case that actually needs `SELECT ... FOR UPDATE`.

    With the cart already present, no insert conflict serializes anything. Two
    read-committed transactions would both read revision 0, both pass the
    staleness check and both write revision 1 — a lost update in which a
    customer's line silently replaces another's. The row lock is what makes the
    second reader wait until it can see revision 1 and be refused.
    """

    session_id = f"cart-update-{uuid.uuid4().hex}"
    store = PostgresCartStore()
    store.replace(scope=LEGACY_DEFAULT_SCOPE, session_id=session_id, expected_revision=0, lines=[])
    assert store.get(scope=LEGACY_DEFAULT_SCOPE, session_id=session_id)["revision"] == 1

    try:
        assert _race(session_id, expected_revision=1) == ["cart_revision_conflict", "committed"]
        current = PostgresCartStore().get(scope=LEGACY_DEFAULT_SCOPE, session_id=session_id)
        assert current["revision"] == 2, "both writers committed; one cart update was lost"
        assert current["lines"] == LINES
    finally:
        _purge(session_id)
