"""Durable aggregate storage for the store-scoped RAG Intelligence Studio.

The Studio owns one optimistic-concurrency aggregate per tenant/store.  The
JSON adapter keeps local development simple; PostgreSQL uses a JSONB snapshot
with a compare-and-swap revision so concurrent Admin saves cannot overwrite
one another.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID

import config
from repositories import postgres_utils

_LOCK = RLock()


class RagStudioConflictError(RuntimeError):
    """The aggregate changed after the caller loaded it."""


def _path(tenant_id: UUID, store_id: UUID) -> Path:
    return (
        Path(config.LEARNING_DATA_DIR)
        / "rag_studio"
        / f"{tenant_id}_{store_id}.json"
    )


def empty_state(*, tenant_id: UUID, store_id: UUID) -> dict[str, Any]:
    return {
        "schema_version": "rag-studio-v1",
        "revision": 0,
        "tenant_id": str(tenant_id),
        "store_id": str(store_id),
        "items": [],
        "configurations": [],
        "configuration_version_sequence": 0,
        "test_cases": [],
        "evaluation_runs": [],
        "index_health": "empty",
        "online_health": {
            "query_count": 0,
            "zero_result_count": 0,
            "latencies_ms": [],
            "error_count": 0,
            "fallback_count": 0,
        },
    }


def load_state(*, tenant_id: UUID, store_id: UUID) -> dict[str, Any]:
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT revision, state
                FROM rag_studio_states
                WHERE tenant_id = %s AND store_id = %s
                """,
                (tenant_id, store_id),
            )
            row = cur.fetchone()
            if not row:
                return empty_state(tenant_id=tenant_id, store_id=store_id)
            state = dict(row["state"] or {})
            state["revision"] = int(row["revision"])
            return state

    path = _path(tenant_id, store_id)
    with _LOCK:
        if not path.exists():
            return empty_state(tenant_id=tenant_id, store_id=store_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return empty_state(tenant_id=tenant_id, store_id=store_id)
        if not isinstance(payload, dict):
            return empty_state(tenant_id=tenant_id, store_id=store_id)
        return copy.deepcopy(payload)


def save_state(
    state: dict[str, Any],
    *,
    tenant_id: UUID,
    store_id: UUID,
    expected_revision: int,
) -> dict[str, Any]:
    next_state = copy.deepcopy(state)
    next_revision = int(expected_revision) + 1
    next_state["revision"] = next_revision
    next_state["tenant_id"] = str(tenant_id)
    next_state["store_id"] = str(store_id)

    if postgres_utils.use_postgres():
        try:
            from psycopg.types.json import Jsonb
        except Exception as exc:  # pragma: no cover
            raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            if int(expected_revision) == 0:
                cur.execute(
                    """
                    INSERT INTO rag_studio_states (tenant_id, store_id, revision, state)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, store_id) DO NOTHING
                    RETURNING revision
                    """,
                    (tenant_id, store_id, next_revision, Jsonb(next_state)),
                )
            else:
                cur.execute(
                    """
                    UPDATE rag_studio_states
                    SET revision = %s, state = %s, updated_at = NOW()
                    WHERE tenant_id = %s AND store_id = %s AND revision = %s
                    RETURNING revision
                    """,
                    (
                        next_revision,
                        Jsonb(next_state),
                        tenant_id,
                        store_id,
                        int(expected_revision),
                    ),
                )
            if cur.fetchone() is None:
                conn.rollback()
                raise RagStudioConflictError("rag_studio_state_changed")
            conn.commit()
        return next_state

    path = _path(tenant_id, store_id)
    with _LOCK:
        current = load_state(tenant_id=tenant_id, store_id=store_id)
        if int(current.get("revision") or 0) != int(expected_revision):
            raise RagStudioConflictError("rag_studio_state_changed")
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(next_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(path)
    return next_state


def delete_local_states() -> int:
    """Delete only Studio aggregate files; used by the deployment reset command."""

    root = Path(config.LEARNING_DATA_DIR) / "rag_studio"
    if not root.exists():
        return 0
    deleted = 0
    for path in root.glob("*.json"):
        path.unlink(missing_ok=True)
        deleted += 1
    return deleted
