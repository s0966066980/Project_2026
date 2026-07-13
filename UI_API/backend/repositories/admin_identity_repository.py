"""PostgreSQL adapter for scoped Admin identity, RBAC, and sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from repositories import postgres_utils


def _connection():
    if not postgres_utils.use_postgres():
        raise postgres_utils.PostgresUnavailableError("Admin identity requires PostgreSQL storage")
    postgres_utils.init_schema()
    return postgres_utils.connect()


def find_admin_user(tenant_id: UUID, login_identity: str) -> dict | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, login_identity, display_name, password_hash, status,
                   created_at, updated_at
            FROM admin_users
            WHERE tenant_id = %s AND login_identity = %s
            """,
            (tenant_id, login_identity),
        )
        row = cur.fetchone()
        return dict(row) if row is not None else None


def create_admin_user(**values: object) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_users (
                id, tenant_id, login_identity, display_name, password_hash, status
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, login_identity, display_name, status, created_at, updated_at
            """,
            (
                values["user_id"],
                values["tenant_id"],
                values["login_identity"],
                values.get("display_name", ""),
                values["password_hash"],
                values.get("status", "active"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row)


def update_admin_password_hash(user_id: UUID, tenant_id: UUID, password_hash: str) -> bool:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE admin_users
            SET password_hash = %s, updated_at = NOW()
            WHERE id = %s AND tenant_id = %s AND status = 'active'
            RETURNING id
            """,
            (password_hash, user_id, tenant_id),
        )
        changed = cur.fetchone() is not None
        conn.commit()
    return changed


def upsert_admin_permission(permission_id: UUID, machine_name: str, description: str) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_permissions (id, machine_name, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (machine_name) DO UPDATE SET
                description = EXCLUDED.description,
                updated_at = NOW()
            RETURNING id, machine_name, description
            """,
            (permission_id, machine_name, description),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row)


def create_admin_role(**values: object) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_roles (id, tenant_id, code, name, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, tenant_id, code, name, status
            """,
            (
                values["role_id"],
                values["tenant_id"],
                values["code"],
                values["name"],
                values.get("status", "active"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row)


def grant_permission_to_role(tenant_id: UUID, role_id: UUID, permission_id: UUID) -> None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_role_permissions (tenant_id, role_id, permission_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """,
            (tenant_id, role_id, permission_id),
        )
        conn.commit()


def assign_admin_role(**values: object) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_user_role_assignments (
                id, tenant_id, user_id, role_id, store_id, status
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, user_id, role_id, store_id, status
            """,
            (
                values["assignment_id"],
                values["tenant_id"],
                values["user_id"],
                values["role_id"],
                values.get("store_id"),
                values.get("status", "active"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row)


def create_admin_session(**values: object) -> dict:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO admin_sessions (
                id, tenant_id, user_id, token_hash, issued_at, expires_at,
                last_used_at, rotated_from_session_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, user_id, issued_at, expires_at, revoked_at
            """,
            (
                values["session_id"],
                values["tenant_id"],
                values["user_id"],
                values["token_hash"],
                values["issued_at"],
                values["expires_at"],
                values["issued_at"],
                values.get("rotated_from_session_id"),
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return dict(row)


def find_admin_session(token_hash: str) -> dict | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS session_id, s.tenant_id, s.user_id, s.issued_at,
                   s.expires_at, s.revoked_at, u.status AS user_status
            FROM admin_sessions s
            JOIN admin_users u ON u.id = s.user_id AND u.tenant_id = s.tenant_id
            WHERE s.token_hash = %s
            """,
            (token_hash,),
        )
        row = cur.fetchone()
        return dict(row) if row is not None else None


def load_admin_principal(session_id: UUID, now: datetime) -> dict | None:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS session_id, s.tenant_id, s.user_id
            FROM admin_sessions s
            JOIN admin_users u ON u.id = s.user_id AND u.tenant_id = s.tenant_id
            WHERE s.id = %s
              AND s.revoked_at IS NULL
              AND s.expires_at > %s
              AND u.status = 'active'
            """,
            (session_id, now),
        )
        session = cur.fetchone()
        if session is None:
            return None
        cur.execute(
            """
            SELECT DISTINCT r.code
            FROM admin_user_role_assignments a
            JOIN admin_roles r ON r.id = a.role_id AND r.tenant_id = a.tenant_id
            WHERE a.user_id = %s AND a.tenant_id = %s
              AND a.status = 'active' AND r.status = 'active'
            ORDER BY r.code
            """,
            (session["user_id"], session["tenant_id"]),
        )
        roles = [row["code"] for row in cur.fetchall()]
        cur.execute(
            """
            SELECT DISTINCT p.machine_name
            FROM admin_user_role_assignments a
            JOIN admin_roles r ON r.id = a.role_id AND r.tenant_id = a.tenant_id
            JOIN admin_role_permissions rp ON rp.role_id = r.id AND rp.tenant_id = r.tenant_id
            JOIN admin_permissions p ON p.id = rp.permission_id
            WHERE a.user_id = %s AND a.tenant_id = %s
              AND a.status = 'active' AND r.status = 'active'
            ORDER BY p.machine_name
            """,
            (session["user_id"], session["tenant_id"]),
        )
        permissions = [row["machine_name"] for row in cur.fetchall()]
        cur.execute(
            """
            SELECT store_id
            FROM admin_user_role_assignments
            WHERE user_id = %s AND tenant_id = %s AND status = 'active'
            """,
            (session["user_id"], session["tenant_id"]),
        )
        assigned_stores = [row["store_id"] for row in cur.fetchall()]
        if None in assigned_stores:
            cur.execute(
                "SELECT id FROM stores WHERE tenant_id = %s AND status = 'active' ORDER BY id",
                (session["tenant_id"],),
            )
            store_ids = [row["id"] for row in cur.fetchall()]
        else:
            store_ids = sorted(set(assigned_stores), key=str)
        cur.execute("UPDATE admin_sessions SET last_used_at = %s WHERE id = %s", (now, session_id))
        conn.commit()
    return {
        "user_id": session["user_id"],
        "tenant_id": session["tenant_id"],
        "allowed_store_ids": store_ids,
        "roles": roles,
        "permissions": permissions,
        "session_id": session["session_id"],
    }


def revoke_admin_session(token_hash: str, revoked_at: datetime) -> bool:
    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE admin_sessions
            SET revoked_at = COALESCE(revoked_at, %s)
            WHERE token_hash = %s
            RETURNING id
            """,
            (revoked_at, token_hash),
        )
        changed = cur.fetchone() is not None
        conn.commit()
    return changed


def rotate_admin_session(
    *,
    old_token_hash: str,
    new_session_id: UUID,
    new_token_hash: str,
    issued_at: datetime,
    expires_at: datetime,
) -> dict | None:
    """Atomically revoke an active session and create its replacement."""

    with _connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, user_id
            FROM admin_sessions
            WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > %s
            FOR UPDATE
            """,
            (old_token_hash, issued_at),
        )
        old = cur.fetchone()
        if old is None:
            return None
        cur.execute(
            """
            INSERT INTO admin_sessions (
                id, tenant_id, user_id, token_hash, issued_at, expires_at,
                last_used_at, rotated_from_session_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, tenant_id, user_id, expires_at
            """,
            (
                new_session_id,
                old["tenant_id"],
                old["user_id"],
                new_token_hash,
                issued_at,
                expires_at,
                issued_at,
                old["id"],
            ),
        )
        replacement = cur.fetchone()
        cur.execute("UPDATE admin_sessions SET revoked_at = %s WHERE id = %s", (issued_at, old["id"]))
        conn.commit()
    return dict(replacement)
