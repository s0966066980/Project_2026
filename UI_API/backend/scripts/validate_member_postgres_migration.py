"""驗證會員資料 PostgreSQL live migration 結果。

用途：
    MEMBER_STORAGE_BACKEND=postgres DATABASE_URL=postgresql://... \
    python backend/scripts/validate_member_postgres_migration.py

可選 smoke write：
    MEMBER_STORAGE_BACKEND=postgres DATABASE_URL=postgresql://... \
    python backend/scripts/validate_member_postgres_migration.py --smoke-write
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from backend.scripts import migrate_member_storage
from repositories import (
    member_repository,
    member_session_repository,
    postgres_utils,
    recommendation_event_repository,
)


REQUIRED_TABLES = [
    "schema_migrations",
    "members",
    "member_sessions",
    "member_orders",
    "member_order_items",
    "member_preferences",
    "recommendation_events",
    "admin_audit_logs",
]

COUNT_KEYS = {
    "members": "members",
    "member_orders": "member_orders",
    "member_order_items": "member_order_items",
    "recommendation_events": "recommendation_events",
}


def _query_value(cur, sql: str, params: tuple = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone() or {}
    return int(row.get("value", 0) or 0)


def fetch_table_names() -> list[str]:
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
            return [str(row.get("table_name") or "") for row in cur.fetchall()]


def fetch_counts() -> dict:
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            return {
                "members": _query_value(cur, "SELECT COUNT(*) AS value FROM members"),
                "member_preferences": _query_value(cur, "SELECT COUNT(*) AS value FROM member_preferences"),
                "member_orders": _query_value(cur, "SELECT COUNT(*) AS value FROM member_orders"),
                "member_order_items": _query_value(cur, "SELECT COUNT(*) AS value FROM member_order_items"),
                "recommendation_events": _query_value(cur, "SELECT COUNT(*) AS value FROM recommendation_events"),
            }


def build_checks(expected: dict, actual: dict, tables: list[str], allow_extra: bool = False) -> list[dict]:
    checks = []
    table_set = set(tables)
    for table in REQUIRED_TABLES:
        checks.append({
            "name": f"table:{table}",
            "ok": table in table_set,
            "expected": "exists",
            "actual": "exists" if table in table_set else "missing",
        })

    for expected_key, actual_key in COUNT_KEYS.items():
        expected_value = int(expected.get(expected_key, 0) or 0)
        actual_value = int(actual.get(actual_key, 0) or 0)
        ok = actual_value >= expected_value if allow_extra else actual_value == expected_value
        checks.append({
            "name": f"count:{actual_key}",
            "ok": ok,
            "expected": f">={expected_value}" if allow_extra else expected_value,
            "actual": actual_value,
        })

    expected_members = int(expected.get("members", 0) or 0)
    actual_preferences = int(actual.get("member_preferences", 0) or 0)
    checks.append({
        "name": "count:member_preferences",
        "ok": actual_preferences >= expected_members if allow_extra else actual_preferences == expected_members,
        "expected": f">={expected_members}" if allow_extra else expected_members,
        "actual": actual_preferences,
    })
    return checks


def _delete_smoke_records(phone: str, event_id: str) -> None:
    with postgres_utils.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM recommendation_events WHERE event_id = %s", (event_id,))
            cur.execute("DELETE FROM members WHERE phone = %s", (phone,))
        conn.commit()


def run_smoke_write() -> dict:
    suffix = uuid.uuid4().hex[:8]
    phone = f"0999{int(uuid.uuid4().int % 1000000):06d}"
    session_id = f"migration_smoke_{suffix}"
    event_id = f"rev_migration_smoke_{suffix}"
    now = datetime.now().isoformat()

    _delete_smoke_records(phone, event_id)
    member_repository.upsert_member({
        "phone": phone,
        "nickname": "migration-smoke",
        "created_at": now,
        "visit_count": 1,
        "total_spend": 100,
        "last_visit_at": now,
        "item_freq": {"MCD001": 1},
        "category_freq": {"測試": 1},
        "pair_freq": {},
        "recent_item_ids": ["MCD001"],
        "preference_updated_at": now,
        "orders": [{
            "session_id": session_id,
            "timestamp": now,
            "cart_ids": ["MCD001"],
            "cart_items": [{"id": "MCD001", "name": "測試品項", "category": "測試", "quantity": 1}],
            "total": 100,
            "order_status": "completed",
            "is_completed": True,
            "recommendation_success": True,
            "is_success": True,
        }],
    })
    member_session_repository.bind_session(session_id, phone)
    recommendation_event_repository.append_recommendation_event({
        "event_id": event_id,
        "recommendation_id": "rec_migration_smoke",
        "session_id": session_id,
        "is_member": True,
        "event_type": "recommendation_shown",
        "surface": "migration_smoke",
        "source": "validation_script",
        "item_id": "MCD001",
        "item_name": "測試品項",
        "category": "測試",
        "rank": 1,
        "score": 1,
        "reasons": ["migration_smoke"],
        "quantity": 1,
        "metadata": {"smoke": True},
        "timestamp": now,
    })

    fetched_member = member_repository.get_member(phone)
    fetched_phone = member_session_repository.get_session_phone(session_id)
    fetched_events = recommendation_event_repository.get_recommendation_events(session_id=session_id, limit=10)
    member_session_repository.clear_session(session_id)
    _delete_smoke_records(phone, event_id)

    checks = [
        {"name": "smoke:member_read", "ok": bool(fetched_member and fetched_member.get("phone") == phone)},
        {"name": "smoke:session_read", "ok": fetched_phone == phone},
        {"name": "smoke:event_read", "ok": any(event.get("event_id") == event_id for event in fetched_events)},
    ]
    return {
        "phone": phone,
        "session_id": session_id,
        "event_id": event_id,
        "checks": checks,
        "ok": all(check["ok"] for check in checks),
    }


def validate(
    members_path: Path,
    recommendation_events_path: Path,
    *,
    allow_extra: bool = False,
    smoke_write: bool = False,
) -> dict:
    if postgres_utils.storage_backend() != "postgres":
        return {
            "status": "failed",
            "error": "set MEMBER_STORAGE_BACKEND=postgres before validation",
        }
    try:
        postgres_utils.init_schema()
        expected = migrate_member_storage.build_plan(members_path, recommendation_events_path)
        tables = fetch_table_names()
        actual = fetch_counts()
        checks = build_checks(expected, actual, tables, allow_extra=allow_extra)
        smoke = run_smoke_write() if smoke_write else None
        if smoke:
            checks.extend(smoke["checks"])
        return {
            "status": "passed" if all(check.get("ok") for check in checks) else "failed",
            "mode": "allow_extra" if allow_extra else "strict",
            "expected": expected,
            "actual": actual,
            "tables": tables,
            "checks": checks,
            "smoke_write": smoke,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate PostgreSQL membership live migration.")
    parser.add_argument(
        "--members-path",
        default=str(ROOT_DIR / "learning_data" / "members.json"),
        help="Path to members.json",
    )
    parser.add_argument(
        "--recommendation-events-path",
        default=str(ROOT_DIR / "learning_data" / "recommendation_events.json"),
        help="Path to recommendation_events.json",
    )
    parser.add_argument("--allow-extra", action="store_true", help="Allow DB counts to be greater than JSON counts.")
    parser.add_argument("--smoke-write", action="store_true", help="Run a temporary write/read/delete smoke test.")
    args = parser.parse_args()

    result = validate(
        Path(args.members_path),
        Path(args.recommendation_events_path),
        allow_extra=args.allow_extra,
        smoke_write=args.smoke_write,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
