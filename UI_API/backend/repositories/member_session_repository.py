"""會員 session repository.

JSON 模式維持既有記憶體 session 行為；PostgreSQL 模式會把
`session_id -> phone` 寫入 member_sessions，讓多 worker / 重啟後可恢復。
"""
from datetime import datetime

from repositories import postgres_utils


def bind_session(session_id: str, phone: str) -> None:
    if not postgres_utils.use_postgres():
        return
    postgres_utils.init_schema()
    now = datetime.now().isoformat()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO member_sessions (session_id, phone, created_at, updated_at, cleared_at)
                VALUES (%s, %s, %s, %s, '')
                ON CONFLICT (session_id) DO UPDATE SET
                    phone = EXCLUDED.phone,
                    updated_at = EXCLUDED.updated_at,
                    cleared_at = ''
                """,
                (str(session_id or ""), str(phone or ""), now, now),
            )
        conn.commit()


def get_session_phone(session_id: str) -> str:
    if not postgres_utils.use_postgres():
        return ""
    postgres_utils.init_schema()
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT phone
                FROM member_sessions
                WHERE session_id = %s AND cleared_at = ''
                """,
                (str(session_id or ""),),
            )
            row = cur.fetchone()
    return str(row.get("phone") or "") if row else ""


def clear_session(session_id: str) -> None:
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
                WHERE session_id = %s
                """,
                (now, now, str(session_id or "")),
            )
        conn.commit()
