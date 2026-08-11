from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from models.commercial_scope import CommercialScope


def _scope_ids(scope: CommercialScope) -> tuple[str, str]:
    if scope.store_id is None:
        raise ValueError("store_scope_required")
    return str(scope.tenant_id), str(scope.store_id)


def _record(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class SQLRetrievalConfigurationStore:
    def _connect(self):
        raise NotImplementedError

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, *, scope: CommercialScope) -> dict[str, Any] | None:
        tenant_id, store_id = _scope_ids(scope)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM retrieval_configurations WHERE tenant_id = ? AND store_id = ?",
                (tenant_id, store_id),
            ).fetchone()
            return _record(row)
        finally:
            connection.close()

    def save(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO retrieval_configurations (
                    tenant_id, store_id, version, method, top_k,
                    relevance_policy, preset_version, index_version,
                    published_at, published_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, store_id) DO UPDATE SET
                    version = excluded.version,
                    method = excluded.method,
                    top_k = excluded.top_k,
                    relevance_policy = excluded.relevance_policy,
                    preset_version = excluded.preset_version,
                    index_version = excluded.index_version,
                    published_at = excluded.published_at,
                    published_by = excluded.published_by
                """,
                (
                    tenant_id,
                    store_id,
                    record["version"],
                    record["method"],
                    record["top_k"],
                    record["relevance_policy"],
                    record["preset_version"],
                    record["index_version"],
                    record["published_at"],
                    record["published_by"],
                ),
            )
        return self.get(scope=scope) or {}

    def delete(self, *, scope: CommercialScope, version: int) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM retrieval_configurations WHERE tenant_id = ? AND store_id = ? AND version = ?",
                (tenant_id, store_id, version),
            )
            if int(cursor.rowcount or 0) != 1:
                raise ValueError("configuration_not_found")
        return {"deleted_version": int(version), "was_published": True}
