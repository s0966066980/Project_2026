from contextlib import contextmanager

from repositories import postgres_utils

from .sqlite_store import SQLiteCartStore


class _Conn:
    def __init__(self, c):
        self.c = c

    def execute(self, q, p=()):
        return self.c.execute(q.replace("?", "%s"), p)

    def executemany(self, q, p):
        # psycopg exposes executemany on the cursor only, unlike sqlite3 where
        # the connection forwards it. Replacing an empty cart sends no rows.
        rows = list(p)
        if not rows:
            return None
        with self.c.cursor() as cursor:
            cursor.executemany(q.replace("?", "%s"), rows)
        return None

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


class PostgresCartStore(SQLiteCartStore):
    def __init__(self):
        # PostgreSQL schema is managed only by explicit migration commands.
        pass

    def _insert_cart_if_missing(self, conn, *, tenant, store, session_id, at):
        conn.execute(
            "INSERT INTO ordering_carts VALUES (?,?,?,0,'open',?,?) ON CONFLICT (tenant_id,store_id,session_id) DO NOTHING",
            (tenant, store, session_id, at, at),
        )

    def _cart_lock_clause(self) -> str:
        return " FOR UPDATE"

    def _connect(self):
        return _Conn(postgres_utils.connect())

    @contextmanager
    def transaction(self):
        c = self._connect()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()
