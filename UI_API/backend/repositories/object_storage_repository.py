"""PostgreSQL persistence for object storage metadata (not binary bytes)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from models.object_storage import ObjectMetadata
from repositories import postgres_utils


def _row_to_meta(row: dict) -> ObjectMetadata:
    store_raw = row.get("store_id")
    return ObjectMetadata(
        object_id=str(row["object_id"]),
        tenant_id=UUID(str(row["tenant_id"])),
        store_id=UUID(str(store_raw)) if store_raw else None,
        owner=str(row.get("owner") or ""),
        content_type=str(row["content_type"]),
        size=int(row["size_bytes"]),
        checksum=str(row["checksum"]),
        encryption=str(row["encryption"]),
        retention_days=int(row["retention_days"]),
        created_at=row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        deleted_at=(
            row["deleted_at"].isoformat()
            if row.get("deleted_at") is not None and hasattr(row["deleted_at"], "isoformat")
            else str(row.get("deleted_at") or "")
        ),
        key_version=str(row.get("key_version") or ""),
        provider=str(row.get("provider") or ""),
        bucket=str(row.get("bucket") or ""),
        provider_key=str(row.get("provider_key") or ""),
    )


def upsert_metadata(meta: ObjectMetadata) -> None:
    if not postgres_utils.use_postgres():
        return
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO object_storage_metadata (
                object_id, tenant_id, store_id, owner, content_type, size_bytes,
                checksum, encryption, key_version, retention_days, provider, bucket,
                provider_key, created_at, deleted_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, NULL
            )
            ON CONFLICT (object_id) DO UPDATE SET
                owner = EXCLUDED.owner,
                content_type = EXCLUDED.content_type,
                size_bytes = EXCLUDED.size_bytes,
                checksum = EXCLUDED.checksum,
                encryption = EXCLUDED.encryption,
                key_version = EXCLUDED.key_version,
                retention_days = EXCLUDED.retention_days,
                provider = EXCLUDED.provider,
                bucket = EXCLUDED.bucket,
                provider_key = EXCLUDED.provider_key,
                deleted_at = NULL
            """,
            (
                meta.object_id,
                meta.tenant_id,
                meta.store_id,
                meta.owner,
                meta.content_type,
                meta.size,
                meta.checksum,
                meta.encryption,
                meta.key_version,
                meta.retention_days,
                meta.provider,
                meta.bucket,
                meta.provider_key,
                datetime.fromisoformat(meta.created_at.replace("Z", "+00:00"))
                if meta.created_at
                else datetime.now(timezone.utc),
            ),
        )
        conn.commit()


def get_metadata(object_id: str, *, tenant_id: UUID) -> ObjectMetadata | None:
    if not postgres_utils.use_postgres():
        return None
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM object_storage_metadata
            WHERE object_id = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (object_id, tenant_id),
        )
        row = cur.fetchone()
    return _row_to_meta(dict(row)) if row else None


def mark_deleted(object_id: str, *, tenant_id: UUID) -> bool:
    if not postgres_utils.use_postgres():
        return False
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE object_storage_metadata
            SET deleted_at = NOW()
            WHERE object_id = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (object_id, tenant_id),
        )
        updated = cur.rowcount > 0
        conn.commit()
    return updated
