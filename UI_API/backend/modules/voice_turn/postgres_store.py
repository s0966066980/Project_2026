from __future__ import annotations

from contextlib import contextmanager

from repositories import postgres_utils

from .sqlite_store import SQLiteVoiceTurnStore


class _Connection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, statement, parameters=()):
        return self._connection.execute(statement.replace("?", "%s"), parameters)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._connection.__exit__(exc_type, exc, traceback)


class PostgresVoiceTurnStore(SQLiteVoiceTurnStore):
    def __init__(self):
        # PostgreSQL schema is managed only by explicit migration commands.
        pass

    def _connect(self):
        return _Connection(postgres_utils.connect())

    @contextmanager
    def _transaction(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
