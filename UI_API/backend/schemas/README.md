# Backend Schemas 與 Migration

`UI_API/backend/schemas/` 保存資料庫 schema、migration 資產與逐步擴大的跨層資料契約。

## 目前內容

- `membership_postgres.sql`：Milestone 1A 前的 legacy membership snapshot，不再作為正式 schema source，也不與每次 migration 手動同步。
- `migrations/*.sql`：不可變、連續版本的正式 schema source of truth。
- `backend/scripts/manage_postgres_migrations.py`：status、validate 與 apply 入口。

## 規則

- 新資料表使用明確主鍵、必要 foreign key/index，以及可排序的 `created_at`/`updated_at`。
- 新 schema 變更使用新的 versioned migration；已套用 migration 不直接改寫。
- Migration 應有版本保護、checksum/重複執行策略與資料驗證。
- 破壞性變更採 `expand → dual write/backfill → verify → switch read → contract`。
- Migration PR 必須說明 backup、restore、rollback 或 roll-forward。
- 新 API request/response 與大型跨層 contract 使用 Pydantic model、TypedDict 或 dataclass，避免無型別 `dict` 擴散。
- 商用資料逐步加入 `tenant_id`、`store_id`、`device_id` scope。
- `0003_admin_identity_rbac_foundation.sql` 是 Admin identity/RBAC schema source；permission/user bootstrap 透過受信任 CLI 執行，不將 password 或 token seed 寫入 migration。
- 會員長期使用 UUID；手機等 PII 的 migration 需搭配加密、lookup hash 與相容計畫。

## 驗證

至少執行對應 migration/repository tests；若影響既有會員或訂單資料，再執行完整 Backend tests。

詳細治理見：

- [架構](../../../docs/ARCHITECTURE.md)
- [PostgreSQL migration 與 recovery](../../../docs/POSTGRESQL_MIGRATIONS.md)
- [商業化治理](../../../docs/COMMERCIAL_GOVERNANCE.md)
- [後續模組](../../../docs/FUTURE_MODULES.md)
