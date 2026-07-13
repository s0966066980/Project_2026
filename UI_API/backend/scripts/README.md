# backend scripts 模組說明

`backend/scripts/` 放置與 UI_API 資料層直接相關的 migration 與 validation script。

## 主要腳本

- `migrate_member_storage.py`：會員資料從 JSON migration 到 PostgreSQL。
- `validate_member_postgres_migration.py`：驗證 PostgreSQL migration 結果。
- `manage_postgres_migrations.py`：檢查、驗證與套用 versioned PostgreSQL schema migration。
- `run_worker.py`：獨立 worker process，消費 `background_jobs` 與 `order_outbox`（claim/retry/DLQ）。

## 維護規則

- 只放正式資料維護腳本。
- demo 或一次性工具放到專案根目錄 `tools/`。
- script 需要能從 `UI_API/` 目錄執行。
- 新增 migration script 時需補測試或 smoke validation。

Migration apply 與 recovery 程序見 [`docs/POSTGRESQL_MIGRATIONS.md`](../../../docs/POSTGRESQL_MIGRATIONS.md)。
