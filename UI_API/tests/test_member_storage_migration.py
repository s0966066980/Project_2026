import importlib
import json


def test_membership_postgres_schema_contains_core_tables():
    from repositories import postgres_utils

    schema = postgres_utils.combined_migration_sql()
    for table in [
        "members",
        "member_sessions",
        "member_orders",
        "member_order_items",
        "member_preferences",
        "recommendation_events",
        "admin_audit_logs",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema


def test_membership_postgres_migrations_are_versioned():
    from repositories import postgres_utils

    files = postgres_utils.migration_files()
    assert [path.name for path in files] == [
        "0001_membership_commercial_baseline.sql",
        "0002_commercial_scope_foundation.sql",
        "0003_admin_identity_rbac_foundation.sql",
        "0004_device_identity_foundation.sql",
    ]
    assert all(postgres_utils.migration_checksum(path) for path in files)


def test_member_migration_dry_run_counts_json_records(tmp_path):
    from backend.scripts import migrate_member_storage
    importlib.reload(migrate_member_storage)

    members_path = tmp_path / "members.json"
    events_path = tmp_path / "recommendation_events.json"
    members_path.write_text(json.dumps([
        {
            "phone": "0912345678",
            "nickname": "小明",
            "item_freq": {"MCD001": 2},
            "orders": [
                {
                    "cart_ids": ["MCD001", "MCD012"],
                    "cart_items": [{"id": "MCD001", "quantity": 2}],
                    "order_status": "completed",
                    "is_completed": True,
                },
                {
                    "cart_ids": ["MCD030"],
                    "order_status": "cancelled",
                    "is_completed": False,
                },
            ],
        }
    ], ensure_ascii=False), encoding="utf-8")
    events_path.write_text(json.dumps([
        {"event_id": "rev_1", "event_type": "recommendation_shown"},
        {"event_id": "rev_2", "event_type": "recommendation_checked_out"},
    ]), encoding="utf-8")

    plan = migrate_member_storage.build_plan(members_path, events_path)

    assert plan == {
        "members": 1,
        "member_orders": 2,
        "completed_orders": 1,
        "cancelled_orders": 1,
        "member_order_items": 2,
        "recommendation_events": 2,
    }


def test_member_session_repository_noops_in_json_backend(monkeypatch):
    from repositories import member_session_repository
    importlib.reload(member_session_repository)

    monkeypatch.setattr(member_session_repository.postgres_utils, "use_postgres", lambda: False)

    member_session_repository.bind_session("s1", "0912345678")
    assert member_session_repository.get_session_phone("s1") == ""
    member_session_repository.clear_session("s1")


def test_validate_migration_build_checks_strict_and_allow_extra():
    from backend.scripts import validate_member_postgres_migration
    importlib.reload(validate_member_postgres_migration)

    expected = {
        "members": 2,
        "member_orders": 3,
        "member_order_items": 4,
        "recommendation_events": 5,
    }
    actual = {
        "members": 3,
        "member_preferences": 3,
        "member_orders": 3,
        "member_order_items": 4,
        "recommendation_events": 5,
    }
    tables = list(validate_member_postgres_migration.REQUIRED_TABLES)

    strict_checks = validate_member_postgres_migration.build_checks(expected, actual, tables)
    assert any(check["name"] == "count:members" and check["ok"] is False for check in strict_checks)

    relaxed_checks = validate_member_postgres_migration.build_checks(expected, actual, tables, allow_extra=True)
    assert all(check["ok"] for check in relaxed_checks)


def test_validate_migration_reports_missing_tables():
    from backend.scripts import validate_member_postgres_migration
    importlib.reload(validate_member_postgres_migration)

    checks = validate_member_postgres_migration.build_checks(
        {"members": 0, "member_orders": 0, "member_order_items": 0, "recommendation_events": 0},
        {"members": 0, "member_preferences": 0, "member_orders": 0, "member_order_items": 0, "recommendation_events": 0},
        ["members"],
    )

    assert any(check["name"] == "table:member_sessions" and check["ok"] is False for check in checks)
