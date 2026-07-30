from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .module import CheckoutError

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS checkout_quotes(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,quote_id TEXT NOT NULL,session_id TEXT NOT NULL,cart_revision INTEGER NOT NULL,status TEXT NOT NULL,lines_json TEXT NOT NULL,pricing_json TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,consumed_order_id TEXT NOT NULL DEFAULT '',PRIMARY KEY(tenant_id,store_id,quote_id));
CREATE UNIQUE INDEX IF NOT EXISTS checkout_one_active_quote ON checkout_quotes(tenant_id,store_id,session_id) WHERE status='active';
CREATE TABLE IF NOT EXISTS checkout_confirmation_attempts(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,quote_id TEXT NOT NULL,outcome_type TEXT NOT NULL,outcome_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(tenant_id,store_id,idempotency_key));
CREATE TABLE IF NOT EXISTS checkout_pickup_sequences(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,last_number INTEGER NOT NULL CHECK(last_number > 0),PRIMARY KEY(tenant_id,store_id));
CREATE TABLE IF NOT EXISTS confirmed_orders(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,order_id TEXT NOT NULL,quote_id TEXT NOT NULL,session_id TEXT NOT NULL,pickup_number INTEGER NOT NULL,status TEXT NOT NULL,lines_json TEXT NOT NULL,pricing_json TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(tenant_id,store_id,order_id),UNIQUE(tenant_id,store_id,quote_id));
CREATE TABLE IF NOT EXISTS checkout_outbox(tenant_id TEXT NOT NULL,store_id TEXT NOT NULL,event_id TEXT NOT NULL,event_type TEXT NOT NULL,aggregate_id TEXT NOT NULL,payload_json TEXT NOT NULL,created_at TEXT NOT NULL,published_at TEXT,PRIMARY KEY(tenant_id,store_id,event_id));
"""


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _json(value):
    return value if isinstance(value, (dict, list)) else json.loads(value)


class SQLiteCheckoutStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self._connect() as c:
            c.executescript(SCHEMA)
            columns = {row["name"] for row in c.execute("PRAGMA table_info(confirmed_orders)").fetchall()}
            if "pickup_number" not in columns:
                c.execute("ALTER TABLE confirmed_orders ADD COLUMN pickup_number INTEGER NOT NULL DEFAULT 0")

    def _connect(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    @contextmanager
    def tx(self):
        c = self._connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def prepare(self, *, scope, session_id, cart_revision, lines, pricing, ttl_seconds):
        t, s = str(scope.tenant_id), str(scope.store_id)
        now = _now()
        exp = (now + timedelta(seconds=ttl_seconds)).isoformat()
        with self.tx() as c:
            existing = c.execute(
                "SELECT * FROM checkout_quotes WHERE tenant_id=? AND store_id=? AND session_id=? AND status='active'",
                (t, s, session_id),
            ).fetchone()
            if (
                existing
                and int(existing["cart_revision"]) == cart_revision
                and _iso(existing["expires_at"]) > now.isoformat()
            ):
                return self._quote(existing)
            c.execute(
                "UPDATE checkout_quotes SET status='superseded' WHERE tenant_id=? AND store_id=? AND session_id=? AND status='active'",
                (t, s, session_id),
            )
            q = str(uuid4())
            c.execute(
                "INSERT INTO checkout_quotes VALUES(?,?,?,?,?,'active',?,?,?,?, '')",
                (
                    t,
                    s,
                    q,
                    session_id,
                    cart_revision,
                    json.dumps(lines, separators=(",", ":")),
                    json.dumps(pricing, separators=(",", ":")),
                    now.isoformat(),
                    exp,
                ),
            )
        return self.outcome(scope=scope, quote_id=q, idempotency_key="")

    def outcome(self, *, scope, quote_id, idempotency_key):
        t, s = str(scope.tenant_id), str(scope.store_id)
        with self._connect() as c:
            if idempotency_key:
                a = c.execute(
                    "SELECT outcome_json FROM checkout_confirmation_attempts WHERE tenant_id=? AND store_id=? AND idempotency_key=?",
                    (t, s, idempotency_key),
                ).fetchone()
                if a:
                    return _json(a["outcome_json"])
            q = c.execute(
                "SELECT * FROM checkout_quotes WHERE tenant_id=? AND store_id=? AND quote_id=?", (t, s, quote_id)
            ).fetchone()
            if not q:
                raise CheckoutError("quote_not_found")
            result = self._quote(q)
            if q["consumed_order_id"]:
                o = c.execute(
                    "SELECT * FROM confirmed_orders WHERE tenant_id=? AND store_id=? AND order_id=?",
                    (t, s, q["consumed_order_id"]),
                ).fetchone()
                result["order"] = self._order(o)
            return result

    def confirm(self, *, scope, quote_id, idempotency_key, unavailable):
        t, s = str(scope.tenant_id), str(scope.store_id)
        now = _now().isoformat()
        with self.tx() as c:
            attempt = c.execute(
                "SELECT quote_id,outcome_json FROM checkout_confirmation_attempts WHERE tenant_id=? AND store_id=? AND idempotency_key=?",
                (t, s, idempotency_key),
            ).fetchone()
            if attempt:
                if str(attempt["quote_id"]) != quote_id:
                    raise CheckoutError("idempotency_conflict")
                return _json(attempt["outcome_json"])
            q = c.execute(
                "SELECT * FROM checkout_quotes WHERE tenant_id=? AND store_id=? AND quote_id=?", (t, s, quote_id)
            ).fetchone()
            if not q:
                raise CheckoutError("quote_not_found")
            if q["consumed_order_id"]:
                o = c.execute(
                    "SELECT * FROM confirmed_orders WHERE tenant_id=? AND store_id=? AND order_id=?",
                    (t, s, q["consumed_order_id"]),
                ).fetchone()
                return {"type": "confirmed", "order": self._order(o), "replayed": True}
            if q["status"] != "active":
                result = {"type": f"quote_{q['status']}"}
            elif _iso(q["expires_at"]) <= now:
                c.execute(
                    "UPDATE checkout_quotes SET status='expired' WHERE tenant_id=? AND store_id=? AND quote_id=?",
                    (t, s, quote_id),
                )
                result = {"type": "quote_expired"}
            else:
                cart = c.execute(
                    "SELECT revision,status FROM ordering_carts WHERE tenant_id=? AND store_id=? AND session_id=?",
                    (t, s, q["session_id"]),
                ).fetchone()
                if not cart or cart["status"] != "open" or int(cart["revision"]) != int(q["cart_revision"]):
                    c.execute(
                        "UPDATE checkout_quotes SET status='stale' WHERE tenant_id=? AND store_id=? AND quote_id=?",
                        (t, s, quote_id),
                    )
                    result = {"type": "quote_stale"}
                elif unavailable:
                    result = {"type": "items_unavailable", "items": unavailable}
                else:
                    oid = str(uuid4())
                    pickup_number = self._next_pickup_number(c, tenant_id=t, store_id=s)
                    lines = _json(q["lines_json"])
                    pricing = _json(q["pricing_json"])
                    c.execute(
                        "INSERT INTO confirmed_orders(tenant_id,store_id,order_id,quote_id,session_id,pickup_number,status,lines_json,pricing_json,created_at) VALUES(?,?,?,?,?,?,'payment_pending',?,?,?)",
                        (t, s, oid, quote_id, q["session_id"], pickup_number, q["lines_json"], q["pricing_json"], now),
                    )
                    c.execute(
                        "UPDATE checkout_quotes SET status='consumed',consumed_order_id=? WHERE tenant_id=? AND store_id=? AND quote_id=?",
                        (oid, t, s, quote_id),
                    )
                    c.execute(
                        "UPDATE ordering_carts SET status='closed',updated_at=? WHERE tenant_id=? AND store_id=? AND session_id=?",
                        (now, t, s, q["session_id"]),
                    )
                    event = {
                        "order_id": oid,
                        "pickup_number": pickup_number,
                        "quote_id": quote_id,
                        "session_id": q["session_id"],
                    }
                    c.execute(
                        "INSERT INTO checkout_outbox VALUES(?,?,?,'OrderConfirmed',?,?,?,NULL)",
                        (t, s, str(uuid4()), oid, json.dumps(event, separators=(",", ":")), now),
                    )
                    result = {
                        "type": "confirmed",
                        "order": {
                            "order_id": oid,
                            "pickup_number": pickup_number,
                            "quote_id": quote_id,
                            "session_id": q["session_id"],
                            "status": "payment_pending",
                            "lines": lines,
                            "pricing": pricing,
                        },
                        "replayed": False,
                    }
            c.execute(
                "INSERT INTO checkout_confirmation_attempts VALUES(?,?,?,?,?,?,?)",
                (t, s, idempotency_key, quote_id, result["type"], json.dumps(result, separators=(",", ":")), now),
            )
        return result

    @staticmethod
    def _next_pickup_number(c, *, tenant_id: str, store_id: str) -> int:
        row = c.execute(
            """
            INSERT INTO checkout_pickup_sequences(tenant_id,store_id,last_number)
            VALUES(?,?,1)
            ON CONFLICT(tenant_id,store_id)
            DO UPDATE SET last_number=checkout_pickup_sequences.last_number + 1
            RETURNING checkout_pickup_sequences.last_number
            """,
            (tenant_id, store_id),
        ).fetchone()
        if row is None:
            raise CheckoutError("pickup_number_unavailable")
        return int(row["last_number"])

    def pending_outbox(self, *, limit: int = 100):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tenant_id,store_id,event_id,event_type,aggregate_id,payload_json FROM checkout_outbox WHERE published_at IS NULL ORDER BY created_at LIMIT ?",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [
            {
                "tenant_id": str(row["tenant_id"]),
                "store_id": str(row["store_id"]),
                "event_id": str(row["event_id"]),
                "event_type": row["event_type"],
                "aggregate_id": str(row["aggregate_id"]),
                "payload": _json(row["payload_json"]),
            }
            for row in rows
        ]

    def mark_outbox_published(self, *, event_id: str):
        with self.tx() as conn:
            conn.execute(
                "UPDATE checkout_outbox SET published_at=? WHERE event_id=? AND published_at IS NULL",
                (_now().isoformat(), event_id),
            )

    @staticmethod
    def _quote(q):
        return {
            "quote_id": str(q["quote_id"]),
            "session_id": q["session_id"],
            "cart_revision": int(q["cart_revision"]),
            "status": q["status"],
            "lines": _json(q["lines_json"]),
            "pricing": _json(q["pricing_json"]),
            "expires_at": _iso(q["expires_at"]),
        }

    @staticmethod
    def _order(o):
        return {
            "order_id": str(o["order_id"]),
            "pickup_number": int(o["pickup_number"]),
            "quote_id": str(o["quote_id"]),
            "session_id": o["session_id"],
            "status": o["status"],
            "lines": _json(o["lines_json"]),
            "pricing": _json(o["pricing_json"]),
        }
