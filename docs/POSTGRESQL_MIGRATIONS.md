# PostgreSQL Migration Foundation

- 狀態：Active
- 適用範圍：`UI_API/backend/schemas/migrations/*.sql`
- Owner：Backend / Data / Operations

本文件定義 Project_2026 的 PostgreSQL migration status、migration validate、apply、migration lock、checksum validation、idempotency 與 backup/recovery documentation。Milestone 1A 只強化 migration framework，不新增或修改產品 Schema。

## Migration Contract

- Migration 檔名使用四位數連續版本與小寫 snake case，例如 `0002_add_order_reference.sql`。
- 已在任何共用環境套用的 migration 不得修改、刪除或重新編號；變更使用新的 forward migration。
- Schema migration 與大規模 data backfill 分開，並採 `expand → dual write/backfill → verify → switch read → contract`。
- Apply 前驗證本地版本連續性、資料庫已套用版本、SHA-256 checksum 與 source completeness。
- Apply 在單一 transaction 中取得 PostgreSQL transaction-scoped advisory migration lock，避免多 instance 同時執行。
- 已套用且 checksum 相同的版本會跳過，因此 apply 具 idempotency。
- Checksum mismatch 或資料庫存在但本地缺少的版本是部署阻斷，不得以修改 `schema_migrations` 繞過。

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
