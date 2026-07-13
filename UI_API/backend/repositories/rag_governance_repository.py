"""RAG governance persistence: PostgreSQL source of truth when configured, JSON compatibility otherwise."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import config
from models.rag_governance import RagAssetStatus, RagAssetVersion
from repositories import postgres_utils


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_path() -> Path:
    return Path(config.LEARNING_DATA_DIR) / "rag_asset_versions.json"


def _load_json_rows() -> list[dict[str, Any]]:
    path = _json_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data if isinstance(data, list) else data.get("assets", [])
    return [dict(row) for row in rows if isinstance(row, dict)]


def _save_json_rows(rows: list[dict[str, Any]]) -> None:
    path = _json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def use_durable() -> bool:
    return postgres_utils.use_postgres()


def load_assets() -> list[dict[str, Any]]:
    if not use_durable():
        return _load_json_rows()
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.document_id, d.tenant_id, d.store_id, d.owner, d.source,
                   v.version, v.status, v.checksum, v.content_ref,
                   v.created_at, v.reviewed_at, v.published_at, v.superseded_at,
                   v.last_rebuild_at, v.history,
                   v.extractor_version, v.chunking_version, v.embedding_provider,
                   v.embedding_model, v.embedding_version, v.retrieval_config_version,
                   v.index_version
            FROM rag_document_versions v
            JOIN rag_documents d ON d.document_id = v.document_id
            ORDER BY d.document_id, v.version
            """
        )
        rows = []
        for row in cur.fetchall():
            rows.append(_pg_row_to_asset_dict(dict(row)))
        return rows


def save_assets(rows: list[dict[str, Any]]) -> None:
    """Compatibility bulk save used by JSON path and migration import."""

    if not use_durable():
        _save_json_rows(rows)
        return
    # PostgreSQL path uses granular upserts; bulk save rewrites via upsert each row.
    for row in rows:
        upsert_asset_row(row)


def _pg_row_to_asset_dict(row: dict[str, Any]) -> dict[str, Any]:
    def _ts(value: Any) -> str:
        if value is None:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    history = row.get("history") or []
    if isinstance(history, str):
        try:
            history = json.loads(history)
        except json.JSONDecodeError:
            history = []
    return {
        "document_id": str(row["document_id"]),
        "version": int(row["version"]),
        "status": str(row["status"]),
        "source": str(row.get("source") or ""),
        "checksum": str(row["checksum"]),
        "owner": str(row.get("owner") or ""),
        "tenant_id": str(row["tenant_id"]) if row.get("tenant_id") else None,
        "store_id": str(row["store_id"]) if row.get("store_id") else None,
        "created_at": _ts(row.get("created_at")),
        "reviewed_at": _ts(row.get("reviewed_at")),
        "published_at": _ts(row.get("published_at")),
        "superseded_at": _ts(row.get("superseded_at")),
        "content_ref": str(row.get("content_ref") or ""),
        "history": list(history),
        "last_rebuild_at": _ts(row.get("last_rebuild_at")),
        "extractor_version": str(row.get("extractor_version") or ""),
        "chunking_version": str(row.get("chunking_version") or ""),
        "embedding_provider": str(row.get("embedding_provider") or ""),
        "embedding_model": str(row.get("embedding_model") or ""),
        "embedding_version": str(row.get("embedding_version") or ""),
        "retrieval_config_version": str(row.get("retrieval_config_version") or ""),
        "index_version": str(row.get("index_version") or ""),
    }


def _jsonb(value: object):
    try:
        from psycopg.types.json import Jsonb
    except Exception as exc:  # pragma: no cover
        raise postgres_utils.PostgresUnavailableError("psycopg Jsonb support is required") from exc
    return Jsonb(value)


def upsert_asset_row(row: dict[str, Any]) -> None:
    if not use_durable():
        rows = _load_json_rows()
        replaced = False
        for idx, existing in enumerate(rows):
            if existing.get("document_id") == row.get("document_id") and int(existing.get("version") or 0) == int(
                row.get("version") or 0
            ):
                rows[idx] = dict(row)
                replaced = True
                break
        if not replaced:
            rows.append(dict(row))
        _save_json_rows(rows)
        return

    postgres_utils.init_schema()
    tenant_id = row.get("tenant_id")
    if not tenant_id:
        raise ValueError("tenant_id is required for durable RAG assets")
    store_id = row.get("store_id")
    version_id = uuid4()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_documents (document_id, tenant_id, store_id, owner, source, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (document_id) DO UPDATE SET
                owner = EXCLUDED.owner,
                source = EXCLUDED.source,
                updated_at = NOW()
            """,
            (
                row["document_id"],
                UUID(str(tenant_id)),
                UUID(str(store_id)) if store_id else None,
                str(row.get("owner") or ""),
                str(row.get("source") or ""),
            ),
        )
        cur.execute(
            """
            INSERT INTO rag_document_versions (
                id, document_id, version, status, checksum, content_ref, content_type, size_bytes,
                extractor_version, chunking_version, embedding_provider, embedding_model,
                embedding_version, retrieval_config_version, index_version,
                created_by, reviewed_by, published_by,
                created_at, reviewed_at, published_at, superseded_at, last_rebuild_at, history
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                COALESCE(%s::timestamptz, NOW()), %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_id, version) DO UPDATE SET
                status = EXCLUDED.status,
                checksum = EXCLUDED.checksum,
                content_ref = EXCLUDED.content_ref,
                reviewed_at = EXCLUDED.reviewed_at,
                published_at = EXCLUDED.published_at,
                superseded_at = EXCLUDED.superseded_at,
                last_rebuild_at = EXCLUDED.last_rebuild_at,
                history = EXCLUDED.history,
                extractor_version = EXCLUDED.extractor_version,
                chunking_version = EXCLUDED.chunking_version,
                embedding_provider = EXCLUDED.embedding_provider,
                embedding_model = EXCLUDED.embedding_model,
                embedding_version = EXCLUDED.embedding_version,
                retrieval_config_version = EXCLUDED.retrieval_config_version,
                index_version = EXCLUDED.index_version
            """,
            (
                version_id,
                row["document_id"],
                int(row["version"]),
                str(row["status"]),
                str(row["checksum"]),
                str(row.get("content_ref") or ""),
                str(row.get("content_type") or "text/plain"),
                int(row.get("size_bytes") or 0),
                str(row.get("extractor_version") or ""),
                str(row.get("chunking_version") or ""),
                str(row.get("embedding_provider") or ""),
                str(row.get("embedding_model") or ""),
                str(row.get("embedding_version") or ""),
                str(row.get("retrieval_config_version") or ""),
                str(row.get("index_version") or ""),
                str(row.get("owner") or ""),
                str(row.get("reviewed_by") or ""),
                str(row.get("published_by") or ""),
                row.get("created_at") or None,
                row.get("reviewed_at") or None,
                row.get("published_at") or None,
                row.get("superseded_at") or None,
                row.get("last_rebuild_at") or None,
                _jsonb(list(row.get("history") or [])),
            ),
        )
        if str(row.get("status")) == RagAssetStatus.PUBLISHED.value:
            cur.execute(
                """
                INSERT INTO rag_publications (document_id, published_version, published_at, published_by, index_namespace)
                VALUES (%s, %s, COALESCE(%s::timestamptz, NOW()), %s, %s)
                ON CONFLICT (document_id) DO UPDATE SET
                    published_version = EXCLUDED.published_version,
                    published_at = EXCLUDED.published_at,
                    published_by = EXCLUDED.published_by,
                    index_namespace = EXCLUDED.index_namespace
                """,
                (
                    row["document_id"],
                    int(row["version"]),
                    row.get("published_at") or None,
                    str(row.get("published_by") or row.get("owner") or ""),
                    str(row.get("index_version") or f"{row['document_id']}@v{row['version']}"),
                ),
            )
        conn.commit()


def set_publication_pointer(
    *,
    document_id: str,
    version: int,
    actor: str,
    index_namespace: str = "",
) -> None:
    if not use_durable():
        return
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_publications (document_id, published_version, published_at, published_by, index_namespace)
            VALUES (%s, %s, NOW(), %s, %s)
            ON CONFLICT (document_id) DO UPDATE SET
                published_version = EXCLUDED.published_version,
                published_at = NOW(),
                published_by = EXCLUDED.published_by,
                index_namespace = EXCLUDED.index_namespace
            """,
            (document_id, version, actor, index_namespace or f"{document_id}@v{version}"),
        )
        conn.commit()


def record_retrieval_trace(
    *,
    tenant_id: UUID,
    store_id: UUID | None,
    query_ref: str,
    document_versions: list[str],
    chunk_ids: list[str],
    scores: list[float],
    provider: str,
    latency_ms: float,
    schema_version: str = "retrieval-trace-v1",
) -> UUID:
    if not use_durable():
        return uuid4()
    postgres_utils.init_schema()
    trace_id = uuid4()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_retrieval_traces (
                id, tenant_id, store_id, query_ref, document_versions, chunk_ids, scores,
                provider, latency_ms, schema_version
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                trace_id,
                tenant_id,
                store_id,
                query_ref,
                _jsonb(document_versions),
                _jsonb(chunk_ids),
                _jsonb(scores),
                provider,
                latency_ms,
                schema_version,
            ),
        )
        conn.commit()
    return trace_id


def record_rebuild_run(
    *,
    document_id: str,
    version: int,
    tenant_id: UUID,
    store_id: UUID | None,
    status: str,
    side_effect_id: str,
    safe_error: str = "",
) -> UUID:
    if not use_durable():
        return uuid4()
    postgres_utils.init_schema()
    run_id = uuid4()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rag_rebuild_runs (
                id, document_id, version, tenant_id, store_id, status, side_effect_id, safe_error,
                started_at, finished_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            """,
            (run_id, document_id, version, tenant_id, store_id, status, side_effect_id, safe_error),
        )
        conn.commit()
    return run_id


def to_asset(row: dict[str, Any]) -> RagAssetVersion:
    return RagAssetVersion(
        document_id=str(row.get("document_id") or ""),
        version=int(row.get("version") or 1),
        status=RagAssetStatus(str(row.get("status") or RagAssetStatus.DRAFT.value)),
        source=str(row.get("source") or ""),
        checksum=str(row.get("checksum") or ""),
        owner=str(row.get("owner") or ""),
        tenant_id=UUID(row["tenant_id"]) if row.get("tenant_id") else None,
        store_id=UUID(row["store_id"]) if row.get("store_id") else None,
        created_at=str(row.get("created_at") or ""),
        reviewed_at=str(row.get("reviewed_at") or ""),
        published_at=str(row.get("published_at") or ""),
        superseded_at=str(row.get("superseded_at") or ""),
        content_ref=str(row.get("content_ref") or ""),
        history=list(row.get("history") or []),
    )


def asset_to_row(asset: RagAssetVersion) -> dict[str, Any]:
    return {
        "document_id": asset.document_id,
        "version": asset.version,
        "status": asset.status.value,
        "source": asset.source,
        "checksum": asset.checksum,
        "owner": asset.owner,
        "tenant_id": str(asset.tenant_id) if asset.tenant_id else None,
        "store_id": str(asset.store_id) if asset.store_id else None,
        "created_at": asset.created_at,
        "reviewed_at": asset.reviewed_at,
        "published_at": asset.published_at,
        "superseded_at": asset.superseded_at,
        "content_ref": asset.content_ref,
        "history": list(asset.history),
    }
