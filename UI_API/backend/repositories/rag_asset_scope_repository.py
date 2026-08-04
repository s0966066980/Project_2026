"""Scoped metadata boundary for commercial RAG assets.

Document contents remain in the configured document adapter. This repository
stores ownership metadata only and never stores prompts, embeddings, or PII.
"""

from uuid import uuid4

from models.commercial_scope import CommercialScope
from repositories import postgres_utils


def list_asset_scopes(scope: CommercialScope) -> list[dict]:
    if not postgres_utils.use_postgres():
        return []
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT asset_id, metadata FROM rag_asset_scopes
            WHERE tenant_id = %s AND store_id IS NOT DISTINCT FROM %s
            ORDER BY asset_id
            """,
            (scope.tenant_id, scope.store_id),
        )
        return [{"asset_id": str(row["asset_id"]), "metadata": dict(row["metadata"])} for row in cur.fetchall()]


def save_asset_scope(asset_id: str, metadata: dict, scope: CommercialScope) -> dict:
    if not postgres_utils.use_postgres():
        raise RuntimeError("RAG asset scope metadata requires PostgreSQL storage")
    from psycopg.types.json import Jsonb

    normalized_id = str(asset_id or "").strip()
    if not normalized_id:
        raise ValueError("RAG asset ID is required")
    payload = dict(metadata or {})
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_asset_scopes (id, tenant_id, store_id, asset_id, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, store_id, asset_id) WHERE store_id IS NOT NULL
            DO UPDATE SET metadata = EXCLUDED.metadata, updated_at = NOW()
            RETURNING asset_id
            """,
            (uuid4(), scope.tenant_id, scope.store_id, normalized_id, Jsonb(payload)),
        )
        conn.commit()
    return {"asset_id": normalized_id, "metadata": payload}
