"""會員 session repository.

JSON 模式維持既有記憶體 session 行為；PostgreSQL 模式會把
`session_id -> phone` 寫入 member_sessions，讓多 worker / 重啟後可恢復。
"""

from datetime import datetime

from models.commercial_scope import CommercialScope, CommercialScopeConflictError
from repositories import postgres_utils
from utils.commercial_scope_config import resolve_commercial_scope


def bind_session(session_id: str, phone: str) -> None:
    bind_session_scoped(session_id, phone, resolve_commercial_scope())


def bind_session_scoped(session_id: str, phone: str, scope: CommercialScope) -> None:
    if not postgres_utils.use_postgres():
        return
    postgres_utils.init_schema()
    now = datetime.now().isoformat()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO member_sessions (
                    session_id, phone, tenant_id, store_id, origin_device_id,
                    created_at, updated_at, cleared_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, '')
                ON CONFLICT (session_id) DO UPDATE SET
                    phone = EXCLUDED.phone,
                    tenant_id = EXCLUDED.tenant_id,
                    store_id = EXCLUDED.store_id,
                    origin_device_id = EXCLUDED.origin_device_id,
                    updated_at = EXCLUDED.updated_at,
                    cleared_at = ''
                WHERE member_sessions.tenant_id = EXCLUDED.tenant_id
                  AND member_sessions.store_id = EXCLUDED.store_id
                  AND member_sessions.origin_device_id IS NOT DISTINCT FROM EXCLUDED.origin_device_id
                RETURNING session_id
                """,
                (
                    str(session_id or ""),
                    str(phone or ""),
                    scope.tenant_id,
                    scope.store_id,
                    scope.device_id,
                    now,
                    now,
                ),
            )
            if cur.fetchone() is None:
                raise CommercialScopeConflictError("Session ID is already owned by another commercial scope")
        conn.commit()


def get_session_phone(session_id: str) -> str:
    return get_session_phone_scoped(session_id, resolve_commercial_scope())


def get_session_phone_scoped(session_id: str, scope: CommercialScope) -> str:
    if not postgres_utils.use_postgres():
        return ""
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT phone
                FROM member_sessions
                WHERE session_id = %s
                  AND tenant_id = %s
                  AND store_id = %s
                  AND cleared_at = ''
                """,
                (str(session_id or ""), scope.tenant_id, scope.store_id),
            )
            row = cur.fetchone()
    return str(row.get("phone") or "") if row else ""


def clear_session(session_id: str) -> None:
    clear_session_scoped(session_id, resolve_commercial_scope())


def clear_session_scoped(session_id: str, scope: CommercialScope) -> None:
    if not postgres_utils.use_postgres():
        return
    postgres_utils.init_schema()
    now = datetime.now().isoformat()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE member_sessions
                SET cleared_at = %s, updated_at = %s
                WHERE session_id = %s AND tenant_id = %s AND store_id = %s
                """,
                (now, now, str(session_id or ""), scope.tenant_id, scope.store_id),
            )
        conn.commit()
