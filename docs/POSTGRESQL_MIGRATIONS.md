# PostgreSQL Migration Foundation

- 狀態：Active
- 適用範圍：`UI_API/backend/schemas/migrations/*.sql`
- Owner：Backend / Data / Operations

本文件定義 Project_2026 的 PostgreSQL migration status、migration validate、apply、migration lock、checksum validation、idempotency 與 backup/recovery documentation。Milestone 1A 建立 framework；Milestone 1B 使用 `0002_commercial_scope_foundation.sql` 執行 expand-first commercial scope migration。

`backend/schemas/migrations/*.sql` 是正式 schema source of truth。`membership_postgres.sql` 僅為 legacy snapshot，不應與新 migration 平行手動維護。

## Milestone 1B Scope Matrix

| Table / Storage | Business Owner | Required Scope | Legacy Compatibility | Migration Strategy | Index |
| --- | --- | --- | --- | --- | --- |
| `members` | Tenant | tenant | phone PK 保留 | nullable column + Default Tenant backfill | tenant + phone |
| `member_preferences` | Member | 由 member ownership 繼承 | phone FK 保留 | 本次不重複加入 scope | existing PK |
| `member_sessions` | Store / origin Device | tenant + store + origin device | session ID 保留 | nullable columns + Default Scope backfill | scope + session |
| `member_orders` | Store / origin Device | tenant + store + origin device | order/phone key 保留 | nullable columns + Default Scope backfill | scope + phone |
| `member_order_items` | Order | 由 order ownership 繼承 | order FK 保留 | 本次不重複加入 scope | existing order FK |
| `recommendation_events` | Store / Device | tenant + store + device | event ID 保留 | nullable columns + Default Scope backfill | scope + session |
| `admin_audit_logs` | Tenant / optional Store | tenant + optional store | audit ID 保留 | nullable columns + Default Scope backfill | scope + created_at |
| availability / interaction JSON | Store / Device target | 尚無正式 PostgreSQL table | Default Scope only | 不虛構第二套 schema；後續 migration | N/A |

Nullable scope 是 expand 階段，不代表完整 tenant isolation。進入 enforcement 前必須驗證無 null/orphan rows、切換所有 production callers 至 scoped method，再以新 migration 收緊 constraint。

## Migration Contract

- Migration 檔名使用四位數連續版本與小寫 snake case，例如 `0002_add_order_reference.sql`。
- 已在任何共用環境套用的 migration 不得修改、刪除或重新編號；變更使用新的 forward migration。
- Schema migration 與大規模 data backfill 分開，並採 `expand → dual write/backfill → verify → switch read → contract`。
- Apply 前驗證本地版本連續性、資料庫已套用版本、SHA-256 checksum 與 source completeness。
- Apply 在單一 transaction 中取得 PostgreSQL transaction-scoped advisory migration lock，避免多 instance 同時執行。
- 已套用且 checksum 相同的版本會跳過，因此 apply 具 idempotency。
- Checksum mismatch 或資料庫存在但本地缺少的版本是部署阻斷，不得以修改 `schema_migrations` 繞過。
- 目前 runner 在單一 transaction 內套用 migration；PostgreSQL 不允許其中執行 `CREATE INDEX CONCURRENTLY`。未來對大型既有表建立 index 前，必須先設計並測試明確的 non-transactional migration contract，不得直接把該語句加入現行 migration。

## Commands

從 `UI_API/` 執行，`DATABASE_URL` 僅由 environment 或 Secret Manager 提供：

```bash
python backend/scripts/manage_postgres_migrations.py status
python backend/scripts/manage_postgres_migrations.py validate
python backend/scripts/manage_postgres_migrations.py apply
python backend/scripts/manage_postgres_migrations.py validate --require-clean
```

- `status`：列出 applied、pending、checksum mismatch 與 validation errors，不修改資料庫。
- `validate`：驗證 migration source 與已套用狀態；pending migration 本身不是錯誤。
- `validate --require-clean`：另外要求沒有 pending migration，適合作為 deploy gate。
- `apply`：取得 migration lock、按版本套用 pending migration，再驗證 clean state。

CLI 只輸出 migration metadata，不輸出 `DATABASE_URL`、Password、Token 或資料內容。

## PostgreSQL integration CI

GitHub Actions 使用 disposable PostgreSQL 16 service，且不依賴 production Secret、外部 API、Ollama 或模型：

1. 在全新資料庫執行 migration status 與 migration validate。
2. 套用所有 migration。
3. 對同一資料庫再次 apply，驗證 idempotency。
4. 執行 `validate --require-clean`，確認版本、checksum validation 與 source completeness。

CI-only integration test 位於 `UI_API/tests/postgres_migration_integration.py`，不會被 JSON backend 的預設 test suite 自動收集。

### Milestone 1B Rollback / Roll-forward

- Apply 前依本文件流程完成 backup 並記錄 0001 clean status。
- 0002 只新增 table/column/constraint/index；application rollback 可回到 Default Scope 相容版本，但不直接 drop 已建立 schema。
- 若 validation 發現 orphan、lock 或 scope conflict，停止切換新 callers、保留資料，以新的 versioned migration roll-forward 修正；不得改寫 0002 checksum。
- Reserved default names 可由未來 Admin 修改；migration 的 `ON CONFLICT DO NOTHING` 不會覆寫客製名稱。

### Partial Scope Handling

0002 的標準支援路徑是未含 scope column 的正式 Milestone 1A schema。非標準、手動建立或只有部分 scope 的資料庫，升級前必須先完成資料盤點與備份。已套用的 0002 不得修改；發現 partial scope、orphan 或錯誤 ownership 時，使用新的 forward migration 修正，並以 `validate_commercial_scope.py --require-complete` 作為切換前 gate。

## Backup Before Migration

高風險或 production migration apply 前：

1. 執行 `status` 與 `validate`，先處理任何 checksum/source error。
2. 確認備份目的地具最小權限、容量與加密保護。
3. 建立 custom-format backup：

   ```bash
   bash scripts/backup_postgres.sh
   ```

4. 對輸出檔建立並保存 SHA-256：

   ```bash
   sha256sum backups/postgres/<dump-file>.dump
   ```

5. 使用 `pg_restore --list backups/postgres/<dump-file>.dump` 確認 dump 可讀。
6. 記錄 migration 版本、backup 路徑、checksum、執行者、時間與 change/incident reference。

只有 backup 檔存在不代表可恢復；Production 必須定期在隔離資料庫演練 restore 並記錄結果。

## Recovery and Roll-forward

Production migration 預設 forward-only：

- 程式尚未切換讀取時，先停止 rollout，修正問題並新增新的 forward migration。
- 已完成 expand 但尚未 contract 時，應優先回退 application release，保留向後相容 Schema。
- 不直接修改或刪除已套用 migration，不手動改寫 `schema_migrations.checksum`。
- 破壞性 contract migration 必須在獨立 release 執行，且先確認舊 application 已不再讀寫目標欄位。

需要完整 restore 時：

1. 宣告 maintenance window 並停止所有 application write。
2. 先備份目前失敗狀態，保留 forensic 與 reconciliation 依據。
3. 優先將 backup restore 到新的隔離 database，禁止先覆寫唯一 production database。
4. 驗證 schema migration、row counts、關鍵交易資料與 application smoke checks。
5. 經 Operations/Data owner 核准後才切換連線或執行原地 restore：

   ```bash
   bash scripts/restore_postgres.sh backups/postgres/<dump-file>.dump
   ```

6. 恢復服務後執行 migration status、migration validate、健康檢查與資料 reconciliation。

`restore_postgres.sh` 使用 `pg_restore --clean --if-exists`，會替換目標 database 內既有 objects；目標與 maintenance window 未確認前不得執行。
