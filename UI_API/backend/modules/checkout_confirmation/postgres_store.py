import json
from contextlib import contextmanager

from repositories import postgres_utils

from .sqlite_store import SQLiteCheckoutStore


def _adapt(parameters):
    """把 dict/list 參數序列化成 JSON 字串。

    lines_json、pricing_json 等欄位在 Postgres 是 JSONB，讀回來已經是 dict/list。
    確認訂單時會把報價的定價快照原樣寫入 confirmed_orders，psycopg 無法直接綁定
    dict（cannot adapt type 'dict'），因此在 adapter 這層補上轉換。
    """
    return tuple(
        json.dumps(value, separators=(",", ":")) if isinstance(value, (dict, list)) else value for value in parameters
    )


class _Conn:
    def __init__(self, c):
        self.c = c

    def execute(self, q, p=()):
        return self.c.execute(q.replace("?", "%s"), _adapt(p))

    def commit(self):
        self.c.commit()

    def rollback(self):
        self.c.rollback()

    def close(self):
        self.c.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PostgresCheckoutStore(SQLiteCheckoutStore):
    def __init__(self):
        # Do not inherit SQLite's path-based schema initializer.
        pass

    def _connect(self):
        return _Conn(postgres_utils.connect())

    @contextmanager
    def tx(self):
        c = self._connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def pending_outbox(self, *, limit: int = 100):
        with self.tx() as conn:
            rows = conn.execute(
                """
                SELECT * FROM checkout_outbox
                WHERE published_at IS NULL AND dead_lettered_at IS NULL
                  AND available_at <= NOW()
                  AND (locked_until IS NULL OR locked_until <= NOW())
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            claimed_rows = []
            for row in rows:
                conn.execute(
                    "UPDATE checkout_outbox SET attempt_count=attempt_count+1, locked_by=?, locked_until=NOW() + INTERVAL '60 seconds' WHERE event_id=?",
                    ("checkout-dispatcher", row["event_id"]),
                )
                claimed_rows.append(
                    conn.execute("SELECT * FROM checkout_outbox WHERE event_id=?", (row["event_id"],)).fetchone()
                )
        return [
            {
                "tenant_id": str(row["tenant_id"]),
                "store_id": str(row["store_id"]),
                "event_id": str(row["event_id"]),
                "event_type": row["event_type"],
                "aggregate_id": str(row["aggregate_id"]),
                "payload": row["payload_json"]
                if isinstance(row["payload_json"], dict)
                else json.loads(row["payload_json"]),
                "attempt_count": int(row["attempt_count"] or 0),
                "max_attempts": int(row["max_attempts"] or 5),
            }
            for row in claimed_rows
        ]
