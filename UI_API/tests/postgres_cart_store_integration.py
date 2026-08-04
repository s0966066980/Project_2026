"""PostgreSQL integration for the kiosk ordering cart store.

Guards the checkout path that crashed with
`AttributeError: 'Connection' object has no attribute 'executemany'`:
psycopg exposes ``executemany`` on the cursor only, while the SQLite store the
PostgreSQL store inherits from calls it on the connection.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest


def _schema_url(database_url: str, schema: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def test_cart_replace_writes_lines_on_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    import psycopg

    from models.commercial_scope import LEGACY_DEFAULT_SCOPE
    from modules.cart.postgres_store import PostgresCartStore
    from repositories import postgres_utils

    # The runtime role is intentionally not allowed to run DDL on local pilots,
    # so the throwaway schema is created and used through the migration role.
    base_url = postgres_utils.migration_database_url() or postgres_utils.database_url()
    schema = "cart_store_integration"
    with psycopg.connect(base_url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        conn.execute(f'CREATE SCHEMA "{schema}"')
    scoped_url = _schema_url(base_url, schema)
    monkeypatch.setattr(postgres_utils, "database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "migration_database_url", lambda: scoped_url)
    monkeypatch.setattr(postgres_utils, "storage_backend", lambda: "postgres")
    postgres_utils.init_schema()

    store = PostgresCartStore()
    scope = LEGACY_DEFAULT_SCOPE
    session_id = f"cart-{uuid.uuid4().hex[:8]}"

    assert store.get(scope=scope, session_id=session_id) == {
        "session_id": session_id,
        "revision": 0,
        "status": "open",
        "lines": [],
    }

    lines = [
        {"item_id": "MCD001", "quantity": 2, "applied_offer_id": "", "options": []},
        {"item_id": "MCD030", "quantity": 1, "applied_offer_id": "OFFER1", "options": [{"size": "L"}]},
    ]
    replaced = store.replace(scope=scope, session_id=session_id, expected_revision=0, lines=lines)
    assert replaced["revision"] == 1
    assert store.get(scope=scope, session_id=session_id) == {
        "session_id": session_id,
        "revision": 1,
        "status": "open",
        "lines": lines,
    }

    # Emptying a cart sends no rows to executemany and must still bump the revision.
    emptied = store.replace(scope=scope, session_id=session_id, expected_revision=1, lines=[])
    assert emptied["revision"] == 2
    assert store.get(scope=scope, session_id=session_id)["lines"] == []

    store.close(scope=scope, session_id=session_id, status="closed")
    assert store.get(scope=scope, session_id=session_id)["status"] == "closed"
