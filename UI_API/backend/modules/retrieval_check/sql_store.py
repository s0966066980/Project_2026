from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

from models.commercial_scope import CommercialScope


def _scope_ids(scope: CommercialScope) -> tuple[str, str]:
    if scope.store_id is None:
        raise ValueError("store_scope_required")
    return str(scope.tenant_id), str(scope.store_id)


def _record(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("created_at", "expires_at", "confirmed_at"):
        value = result.get(key)
        if isinstance(value, datetime):
            result[key] = value.isoformat()
    result["eligible"] = bool(result.get("eligible"))
    return result


class SQLRetrievalCheckStore:
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

    def create_check(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO rag_retrieval_checks (
                    tenant_id, store_id, check_id, index_identity,
                    configuration_version, method, top_k, relevance_policy,
                    effective_method, fallback_used, result_fingerprint,
                    result_count, eligible, eligibility_reason, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    store_id,
                    record["check_id"],
                    record["index_identity"],
                    record.get("configuration_version"),
                    record["method"],
                    record["top_k"],
                    record["relevance_policy"],
                    record["effective_method"],
                    record["fallback_used"],
                    record["result_fingerprint"],
                    record["result_count"],
                    bool(record["eligible"]),
                    record["eligibility_reason"],
                    record["created_at"],
                    record["expires_at"],
                ),
            )
        return self.get_check(scope=scope, check_id=record["check_id"]) or {}

    def get_check(self, *, scope: CommercialScope, check_id: str) -> dict[str, Any] | None:
        tenant_id, store_id = _scope_ids(scope)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM rag_retrieval_checks
                WHERE tenant_id = ? AND store_id = ? AND check_id = ?
                """,
                (tenant_id, store_id, check_id),
            ).fetchone()
            return _record(row)
        finally:
            connection.close()

    def mark_confirmed(
        self,
        *,
        scope: CommercialScope,
        check_id: str,
        actor: str,
        confirmed_at: str,
    ) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                UPDATE rag_retrieval_checks
                SET confirmed_at = ?, confirmed_by = ?
                WHERE tenant_id = ? AND store_id = ? AND check_id = ?
                  AND confirmed_at IS NULL
                """,
                (confirmed_at, actor, tenant_id, store_id, check_id),
            )
        return self.get_check(scope=scope, check_id=check_id) or {}

    def latest_confirmation(
        self,
        *,
        scope: CommercialScope,
        index_identity: str,
        configuration_version: int,
    ) -> dict[str, Any] | None:
        tenant_id, store_id = _scope_ids(scope)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT * FROM rag_retrieval_checks
                WHERE tenant_id = ? AND store_id = ?
                  AND index_identity = ? AND configuration_version = ?
                  AND confirmed_at IS NOT NULL
                ORDER BY confirmed_at DESC
                LIMIT 1
                """,
                (tenant_id, store_id, index_identity, configuration_version),
            ).fetchone()
            return _record(row)
        finally:
            connection.close()

    def cleanup_expired(self, *, before: str) -> int:
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM rag_retrieval_checks
                WHERE confirmed_at IS NULL AND expires_at < ?
                """,
                (before,),
            )
            return max(0, int(cursor.rowcount or 0))
