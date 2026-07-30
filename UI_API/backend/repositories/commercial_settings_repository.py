"""Versioned tenant/store-scoped commercial settings persistence."""

from uuid import UUID, uuid4

import config
from models.commercial_scope import CommercialScope, is_legacy_store_scope
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope


def _merge_settings(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_settings(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_settings() -> dict:
    return get_settings_scoped(resolve_commercial_scope())


def get_settings_scoped(scope: CommercialScope) -> dict:
    if postgres_utils.use_postgres():
        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT settings, version
                FROM commercial_settings_versions
                WHERE tenant_id = %s AND (store_id = %s OR store_id IS NULL)
                ORDER BY store_id NULLS LAST, version DESC
                LIMIT 1
                """,
                (scope.tenant_id, scope.store_id),
            )
            row = cur.fetchone()
        # No version yet for this scope: seed from the built-in defaults, never from the JSON
        # file — config.load_settings() itself resolves through here when Postgres is active,
        # and falling back to it would recurse.
        return dict(row["settings"]) if row else dict(config.DEFAULT_SETTINGS)
    if not is_legacy_store_scope(scope):
        return {}
    return dict(config.load_settings())


def list_versions_scoped(scope: CommercialScope, limit: int = 25) -> list[dict]:
    """Newest-first settings versions. The JSON fallback keeps no history and returns nothing."""

    if not postgres_utils.use_postgres():
        return []
    with postgres_utils.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT version, settings, actor_id, created_at
            FROM commercial_settings_versions
            WHERE tenant_id = %s AND (store_id = %s OR store_id IS NULL)
            ORDER BY version DESC
            LIMIT %s
            """,
            (scope.tenant_id, scope.store_id, max(1, min(int(limit), 100))),
        )
        rows = cur.fetchall()
    return [
        {
            "version": int(row["version"]),
            "settings": dict(row["settings"] or {}),
            "actor_id": str(row["actor_id"] or ""),
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        }
        for row in rows
    ]


def get_version_settings(scope: CommercialScope, version: int) -> dict | None:
    for row in list_versions_scoped(scope, limit=100):
        if row["version"] == int(version):
            return row["settings"]
    return None


def save_settings(data: dict, *, actor_id: UUID | None = None) -> dict:
    return save_settings_scoped(data, resolve_commercial_scope(), actor_id=actor_id)


def save_settings_scoped(
    data: dict,
    scope: CommercialScope,
    *,
    actor_id: UUID | None = None,
) -> dict:
    settings = _merge_settings(get_settings_scoped(scope), dict(data or {}))
    if postgres_utils.use_postgres():
        from psycopg.types.json import Jsonb

        with postgres_utils.connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"commercial-settings:{scope.tenant_id}:{scope.store_id}",),
            )
            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM commercial_settings_versions
                WHERE tenant_id = %s AND store_id = %s
                """,
                (scope.tenant_id, scope.store_id),
            )
            version = int((cur.fetchone() or {}).get("next_version") or 1)
            cur.execute(
                """
                INSERT INTO commercial_settings_versions (
                    id, tenant_id, store_id, version, settings, actor_id
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uuid4(), scope.tenant_id, scope.store_id, version, Jsonb(settings), actor_id),
            )
            conn.commit()
        return settings
    if not is_legacy_store_scope(scope):
        raise ValueError("JSON settings storage only supports the legacy Default Scope")
    config.save_settings(settings)
    return dict(config.load_settings())
