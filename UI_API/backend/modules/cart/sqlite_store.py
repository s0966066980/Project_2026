from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .module import CartError

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS ordering_carts (
 tenant_id TEXT NOT NULL, store_id TEXT NOT NULL, session_id TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'open',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY (tenant_id, store_id, session_id)
);
CREATE TABLE IF NOT EXISTS ordering_cart_lines (
 tenant_id TEXT NOT NULL, store_id TEXT NOT NULL, session_id TEXT NOT NULL,
 position INTEGER NOT NULL, item_id TEXT NOT NULL, quantity INTEGER NOT NULL,
 applied_offer_id TEXT NOT NULL DEFAULT '', options_json TEXT NOT NULL DEFAULT '[]',
 PRIMARY KEY (tenant_id, store_id, session_id, position),
 FOREIGN KEY (tenant_id, store_id, session_id) REFERENCES ordering_carts(tenant_id,store_id,session_id) ON DELETE CASCADE
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


class SQLiteCartStore:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def transaction(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get(self, *, scope, session_id):
        tenant, store = str(scope.tenant_id), str(scope.store_id)
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM ordering_carts WHERE tenant_id=? AND store_id=? AND session_id=?",
                (tenant, store, session_id),
            ).fetchone()
            if row is None:
                at = _now()
                conn.execute(
                    "INSERT INTO ordering_carts VALUES (?,?,?,0,'open',?,?)", (tenant, store, session_id, at, at)
                )
                revision, status = 0, "open"
            else:
                revision, status = int(row["revision"]), row["status"]
            lines = conn.execute(
                "SELECT item_id,quantity,applied_offer_id,options_json FROM ordering_cart_lines WHERE tenant_id=? AND store_id=? AND session_id=? ORDER BY position",
                (tenant, store, session_id),
            ).fetchall()
        return {
            "session_id": session_id,
            "revision": revision,
            "status": status,
            "lines": [
                {
                    "item_id": x["item_id"],
                    "quantity": int(x["quantity"]),
                    "applied_offer_id": x["applied_offer_id"],
                    "options": x["options_json"]
                    if isinstance(x["options_json"], list)
                    else json.loads(x["options_json"]),
                }
                for x in lines
            ],
        }

    def _insert_cart_if_missing(self, conn, *, tenant, store, session_id, at):
        conn.execute("INSERT INTO ordering_carts VALUES (?,?,?,0,'open',?,?)", (tenant, store, session_id, at, at))

    def _cart_lock_clause(self) -> str:
        return ""

    def replace(self, *, scope, session_id, expected_revision, lines):
        tenant, store, at = str(scope.tenant_id), str(scope.store_id), _now()
        with self.transaction() as conn:
            row = conn.execute(
                "SELECT revision,status FROM ordering_carts WHERE tenant_id=? AND store_id=? AND session_id=?"
                + self._cart_lock_clause(),
                (tenant, store, session_id),
            ).fetchone()
            if row is None:
                self._insert_cart_if_missing(conn, tenant=tenant, store=store, session_id=session_id, at=at)
                row = conn.execute(
                    "SELECT revision,status FROM ordering_carts WHERE tenant_id=? AND store_id=? AND session_id=?"
                    + self._cart_lock_clause(),
                    (tenant, store, session_id),
                ).fetchone()
            if row is None:
                raise CartError("cart_unavailable")
            current, status = int(row["revision"]), row["status"]
            if status != "open":
                raise CartError("cart_closed")
            if current != expected_revision:
                raise CartError("cart_revision_conflict", details={"current_revision": current})
            revision = current + 1
            conn.execute(
                "UPDATE ordering_carts SET revision=?,updated_at=? WHERE tenant_id=? AND store_id=? AND session_id=?",
                (revision, at, tenant, store, session_id),
            )
            conn.execute(
                "DELETE FROM ordering_cart_lines WHERE tenant_id=? AND store_id=? AND session_id=?",
                (tenant, store, session_id),
            )
            conn.executemany(
                "INSERT INTO ordering_cart_lines VALUES (?,?,?,?,?,?,?,?)",
                [
                    (
                        tenant,
                        store,
                        session_id,
                        i,
                        x["item_id"],
                        x["quantity"],
                        x["applied_offer_id"],
                        json.dumps(x["options"], separators=(",", ":")),
                    )
                    for i, x in enumerate(lines)
                ],
            )
        return {"session_id": session_id, "revision": revision, "status": "open", "lines": lines}

    def close(self, *, scope, session_id, status):
        if status not in {"closed", "abandoned"}:
            raise CartError("invalid_cart_status")
        with self.transaction() as conn:
            conn.execute(
                "UPDATE ordering_carts SET status=?,updated_at=? WHERE tenant_id=? AND store_id=? AND session_id=? AND status='open'",
                (status, _now(), str(scope.tenant_id), str(scope.store_id), session_id),
            )
