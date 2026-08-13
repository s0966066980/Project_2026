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


def test_concurrent_cart_replacements_allow_only_one_stale_revision_writer():
    session_id = f"cart-concurrency-{uuid.uuid4().hex}"
    scope = LEGACY_DEFAULT_SCOPE
    lines = [{"item_id": "coffee", "quantity": 1, "options": [], "applied_offer_id": ""}]
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    lock = threading.Lock()

    def replace_cart():
        store = PostgresCartStore()
        barrier.wait()
        try:
            store.replace(scope=scope, session_id=session_id, expected_revision=0, lines=lines)
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

    try:
        assert sorted(outcomes) == ["cart_revision_conflict", "committed"]
        store = PostgresCartStore()
        current = store.get(scope=scope, session_id=session_id)
        assert current["revision"] == 1
        assert current["lines"] == lines
    finally:
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ordering_carts WHERE tenant_id = %s AND store_id = %s AND session_id = %s",
                (scope.tenant_id, scope.store_id, session_id),
            )
            conn.commit()
