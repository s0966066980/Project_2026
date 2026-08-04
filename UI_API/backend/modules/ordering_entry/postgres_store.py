from contextlib import contextmanager

from repositories import postgres_utils

from .sqlite_store import SQLiteEntryFlowStore


class _Conn:
    def __init__(self, c):
        self.c = c

    def execute(self, q, p=()):
        return self.c.execute(q.replace("?", "%s"), p)

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


class PostgresEntryFlowStore(SQLiteEntryFlowStore):
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
