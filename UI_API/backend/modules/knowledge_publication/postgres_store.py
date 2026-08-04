from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from repositories import postgres_utils

from .sqlite_store import SQLitePublicationStore


class _PostgresConnection:
    """Small DB-API adapter for the SQL shared with the SQLite store."""

    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _sql(statement: str) -> str:
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()):
        return self._connection.execute(self._sql(statement), parameters)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._connection.__exit__(exc_type, exc, traceback)


class PostgresPublicationStore(SQLitePublicationStore):
    """Postgres adapter with the same durable publication semantics as SQLite."""

    def __init__(self):
        # PostgreSQL schema is managed only by explicit migration commands.
        pass

    def _connect(self) -> _PostgresConnection:
        return _PostgresConnection(postgres_utils.connect())

    @contextmanager
    def _transaction(self) -> Iterator[_PostgresConnection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
