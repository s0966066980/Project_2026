"""PostgreSQL adapter for per-device credentials and sessions."""

from __future__ import annotations

from datetime import datetime

from repositories import postgres_utils


def _connection():
    if not postgres_utils.use_postgres():
        raise postgres_utils.PostgresUnavailableError("Device identity requires PostgreSQL storage")
    postgres_utils.init_schema()
    return postgres_utils.connect()


def find_device_credential(key_id: str) -> dict | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id AS credential_id, c.tenant_id, c.store_id, c.device_id,
                   c.key_id, c.credential_hash, c.status, c.expires_at,
                   c.revoked_at, c.rotation_valid_until, d.status AS device_status
            FROM device_credentials c
            JOIN devices d
              ON d.id = c.device_id AND d.store_id = c.store_id AND d.tenant_id = c.tenant_id
            WHERE c.key_id = %s
            """,
            (key_id,),
        )
        row = cur.fetchone()
        return dict(row) if row is not None else None


def create_device_session(**values: object) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO device_sessions (
                id, tenant_id, store_id, device_id, credential_id,
                token_hash, issued_at, expires_at, last_used_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, store_id, device_id, credential_id, issued_at, expires_at
            """,
            (
                values["session_id"],
                values["tenant_id"],
                values["store_id"],
                values["device_id"],
                values["credential_id"],
                values["token_hash"],
                values["issued_at"],
                values["expires_at"],
                values["issued_at"],
            ),
        )
        row = cur.fetchone()
        cur.execute(
            "UPDATE device_credentials SET last_used_at = %s WHERE id = %s",
            (values["issued_at"], values["credential_id"]),
        )
        conn.commit()
    return dict(row)


def find_device_session(token_hash: str, now: datetime) -> dict | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS session_id, s.tenant_id, s.store_id, s.device_id,
                   s.credential_id, s.issued_at, s.expires_at, s.revoked_at,
                   c.status AS credential_status, c.revoked_at AS credential_revoked_at,
                   d.status AS device_status
            FROM device_sessions s
            JOIN device_credentials c
              ON c.id = s.credential_id AND c.device_id = s.device_id
             AND c.store_id = s.store_id AND c.tenant_id = s.tenant_id
            JOIN devices d
              ON d.id = s.device_id AND d.store_id = s.store_id AND d.tenant_id = s.tenant_id
            WHERE s.token_hash = %s
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        if row is not None:
            cur.execute("UPDATE device_sessions SET last_used_at = %s WHERE id = %s", (now, row["session_id"]))
            cur.execute("UPDATE devices SET last_seen_at = %s WHERE id = %s", (now, row["device_id"]))
            conn.commit()
        return dict(row) if row is not None else None


def record_device_event(**values: object) -> None:
    from psycopg.types.json import Jsonb

    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO device_credential_events (
                id, tenant_id, store_id, device_id, credential_id, event_type, metadata, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                values["event_id"],
                values["tenant_id"],
                values["store_id"],
                values["device_id"],
                values.get("credential_id"),
                values["event_type"],
                Jsonb(values.get("metadata", {})),
                values["created_at"],
            ),
        )
        conn.commit()
