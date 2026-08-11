from __future__ import annotations

from typing import Any

from repositories import postgres_utils

from .sql_store import SQLRetrievalConfigurationStore


class _PostgresConnection:
    def __init__(self, connection: Any):
        self._connection = connection

    def execute(self, statement: str, parameters: tuple[Any, ...] = ()):
        return self._connection.execute(statement.replace("?", "%s"), parameters)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


class PostgresRetrievalConfigurationStore(SQLRetrievalConfigurationStore):
    def _connect(self) -> _PostgresConnection:
        return _PostgresConnection(postgres_utils.connect())
