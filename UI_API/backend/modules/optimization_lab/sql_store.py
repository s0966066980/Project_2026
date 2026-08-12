"""Portable SQL persistence for the Optimization Lab."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from models.commercial_scope import CommercialScope


def _scope_ids(scope: CommercialScope) -> tuple[str, str]:
    return str(scope.tenant_id), str(scope.store_id)


def _decode(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("evidence_ids", "rag_hit", "report_json"):
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                pass
    return result


class SQLOptimizationLabStore:
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

    def create_evidence(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO optimization_evidence (
                    evidence_id, tenant_id, store_id, observed_at,
                    transcript_masked, assistant_text_masked, rag_hit,
                    voice_outcome, failure_type, retry_outcome, synthetic,
                    source, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["evidence_id"],
                    tenant_id,
                    store_id,
                    record["observed_at"],
                    record["transcript_masked"],
                    record["assistant_text_masked"],
                    json.dumps(record["rag_hit"], sort_keys=True),
                    record["voice_outcome"],
                    record["failure_type"],
                    record["retry_outcome"],
                    bool(record["synthetic"]),
                    record["source"],
                    record["created_at"],
                    record["expires_at"],
                ),
            )
        return {**record, "tenant_id": tenant_id, "store_id": store_id}

    def list_evidence(
        self,
        *,
        scope: CommercialScope,
        start_at: str,
        end_at: str,
        cutoff_at: str,
        synthetic_only: bool,
    ) -> list[dict[str, Any]]:
        tenant_id, store_id = _scope_ids(scope)
        synthetic_clause = " AND synthetic = ?" if synthetic_only else ""
        params: tuple[Any, ...] = (tenant_id, store_id, start_at, end_at, cutoff_at)
        if synthetic_only:
            params += (True,)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT * FROM optimization_evidence
                WHERE tenant_id = ? AND store_id = ?
                  AND observed_at >= ? AND observed_at < ? AND observed_at <= ?
                  {synthetic_clause}
                ORDER BY observed_at ASC, evidence_id ASC
                """,
                params,
            ).fetchall()
            return [_decode(row) or {} for row in rows]
        finally:
            connection.close()

    def get_evidence(self, *, scope: CommercialScope, evidence_id: str) -> dict[str, Any] | None:
        tenant_id, store_id = _scope_ids(scope)
        connection = self._connect()
        try:
            return _decode(
                connection.execute(
                    "SELECT * FROM optimization_evidence WHERE tenant_id = ? AND store_id = ? AND evidence_id = ?",
                    (tenant_id, store_id, str(evidence_id)),
                ).fetchone()
            )
        finally:
            connection.close()

    def create_snapshot(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO optimization_snapshots (
                    snapshot_id, tenant_id, store_id, store_date, timezone,
                    cutoff_at, partial, evidence_ids, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["snapshot_id"],
                    tenant_id,
                    store_id,
                    record["store_date"],
                    record["timezone"],
                    record["cutoff_at"],
                    bool(record["partial"]),
                    json.dumps(record["evidence_ids"], sort_keys=True),
                    record["created_at"],
                    record["expires_at"],
                ),
            )
        return {**record, "tenant_id": tenant_id, "store_id": store_id}

    def save_report(self, *, scope: CommercialScope, record: dict[str, Any]) -> dict[str, Any]:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO optimization_reports (
                    report_id, tenant_id, store_id, snapshot_id, analyzer_id,
                    analyzer_version, model, effort, data_scope, report_json,
                    created_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["report_id"],
                    tenant_id,
                    store_id,
                    record["snapshot_id"],
                    record["analyzer"]["id"],
                    record["analyzer"]["version"],
                    record["selected_model"],
                    record["selected_effort"],
                    record["data_scope"],
                    json.dumps(record, ensure_ascii=False, sort_keys=True),
                    record["created_at"],
                    record["expires_at"],
                    record["status"],
                ),
            )
        return record

    def get_report(self, *, scope: CommercialScope, report_id: str) -> dict[str, Any] | None:
        tenant_id, store_id = _scope_ids(scope)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT report_json FROM optimization_reports WHERE tenant_id = ? AND store_id = ? AND report_id = ?",
                (tenant_id, store_id, str(report_id)),
            ).fetchone()
            if row is None:
                return None
            value = row["report_json"] if hasattr(row, "keys") else row[0]
            return json.loads(value) if isinstance(value, str) else dict(value)
        finally:
            connection.close()

    def record_egress_audit(self, *, scope: CommercialScope, record: dict[str, Any]) -> None:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO optimization_egress_audits (
                    audit_id, tenant_id, store_id, report_id, analyzer_id,
                    analyzer_version, model, effort, data_scope, evidence_count,
                    evidence_ids, authorization_id, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["audit_id"],
                    tenant_id,
                    store_id,
                    record["report_id"],
                    record["analyzer_id"],
                    record["analyzer_version"],
                    record["model"],
                    record["effort"],
                    record["data_scope"],
                    record["evidence_count"],
                    json.dumps(record["evidence_ids"], sort_keys=True),
                    record["authorization_id"],
                    record["observed_at"],
                ),
            )

    def record_access_audit(self, *, scope: CommercialScope, record: dict[str, Any]) -> None:
        tenant_id, store_id = _scope_ids(scope)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO optimization_access_audits (
                    audit_id, tenant_id, store_id, report_id, evidence_id,
                    actor, step_up_expires_at, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["audit_id"],
                    tenant_id,
                    store_id,
                    record["report_id"],
                    record["evidence_id"],
                    record["actor"],
                    record["step_up_expires_at"],
                    record["observed_at"],
                ),
            )

    def cleanup_expired(self, *, now: str) -> int:
        with self._transaction() as connection:
            total = 0
            # Remove audit rows first because Postgres keeps report foreign-key
            # references; the SQLite adapter uses the same order for parity.
            for table in ("optimization_egress_audits", "optimization_access_audits"):
                cursor = connection.execute(
                    f"""
                    DELETE FROM {table}
                    WHERE report_id IN (
                        SELECT report_id FROM optimization_reports WHERE expires_at <= ?
                    )
                    """,
                    (now,),
                )
                total += int(cursor.rowcount or 0)
            for table in ("optimization_reports", "optimization_snapshots", "optimization_evidence"):
                cursor = connection.execute(f"DELETE FROM {table} WHERE expires_at <= ?", (now,))
                total += int(cursor.rowcount or 0)
            return total
