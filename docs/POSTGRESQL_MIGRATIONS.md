# PostgreSQL Migration Foundation

- 狀態：Active
- 適用範圍：`UI_API/backend/schemas/migrations/*.sql`
- Owner：Backend / Data / Operations

本文件定義 Project_2026 的 PostgreSQL migration status、migration validate、apply、migration lock、checksum validation、idempotency 與 backup/recovery documentation。Milestone 1A 建立 framework；Milestone 1B 使用 `0002_commercial_scope_foundation.sql` 執行 expand-first commercial scope migration。

`backend/schemas/migrations/*.sql` 是正式 schema source of truth。`membership_postgres.sql` 僅為 legacy snapshot，不應與新 migration 平行手動維護。

Milestone 1C 新增不可變的 `0003_admin_identity_rbac_foundation.sql`，以 expand-only table 建立 Admin user、role、permission、store assignment 與 revocable session。Password 與 raw session token 不屬於 migration seed data；permission catalog 與首位 Admin 由受信任 provisioning command 建立。

Milestone 1D 新增不可變的 `0004_device_identity_foundation.sql`，建立 device credential、short-lived session 與 safe credential event。Migration 不 seed raw credential；credential 由具 `device_identity.manage` 的已驗證 Admin 對 active device issue，database 只保存 hash。

Milestone 1E 新增 `0005_commercial_scope_contract_enforcement.sql`。標準 0001–0004 資料先經完整性 validator 驗證，再收緊 core scope `NOT NULL`，並建立 store availability、versioned settings、promotion、interaction/intervention outcome 與 RAG asset ownership metadata。Route scope 只由已驗證 `AdminPrincipal`／`DevicePrincipal` 解析。

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

## Milestone 1E Contract Scope Matrix

| Table | Owner / Required Scope | Contract |
| --- | --- | --- |
| `members` | Tenant | `tenant_id NOT NULL`；phone PK 暫留至 ADR-0004 |
| `member_sessions`, `member_orders` | Tenant + Store + origin Device | ownership columns `NOT NULL` 與 composite FK |
| `recommendation_events` | Tenant + Store + Device | ownership columns `NOT NULL`；query 必須帶 scope |
| `admin_audit_logs` | Tenant + optional Store | tenant `NOT NULL`；store 保持 nullable 以支援 tenant-level audit |
| `store_availability`, `promotion_records` | Store | composite Store/Tenant FK 與 scoped unique/index |
| `commercial_settings_versions` | Tenant 或 Store | append-only version；partial unique index處理 nullable store |
| `interaction_events`, `intervention_outcomes` | Device | composite Device/Store/Tenant FK |
| `rag_asset_scopes` | Tenant 或 Store | 只存 ownership metadata，不存文件內容、prompt 或 embedding |

PostgreSQL RLS 在 1E 明確延後：目前 application 使用共用 database identity，尚無可信的 per-request transaction identity，啟用 RLS 只會形成錯誤安全感。現階段 isolation boundary 是 verified principal → `CommercialScope` → parameterized repository filter + FK/constraint；待 connection identity 與 RLS integration test strategy 成熟後，以新 ADR/migration 導入。

## Migration Contract

- Migration 檔名使用四位數連續版本與小寫 snake case，例如 `0002_add_order_reference.sql`。
- 已在任何共用環境套用的 migration 不得修改、刪除或重新編號；變更使用新的 forward migration。
- Schema migration 與大規模 data backfill 分開，並採 `expand → dual write/backfill → verify → switch read → contract`。
- Apply 前驗證本地版本連續性、資料庫已套用版本、SHA-256 checksum 與 source completeness。
- Apply 在單一 transaction 中取得 PostgreSQL transaction-scoped advisory migration lock，避免多 instance 同時執行。
- 已套用且 checksum 相同的版本會跳過，因此 apply 具 idempotency。
- Checksum mismatch 或資料庫存在但本地缺少的版本是部署阻斷，不得以修改 `schema_migrations` 繞過。
- 目前 runner 在單一 transaction 內套用 migration；PostgreSQL 不允許其中執行 `CREATE INDEX CONCURRENTLY`。未來對大型既有表建立 index 前，必須先設計並測試明確的 non-transactional migration contract，不得直接把該語句加入現行 migration。

## Milestone 6B–6D Control Plane Durable Persistence

Migration `0011_control_plane_durable_persistence.sql` establishes:

- Recommendation strategy versions, durable experiment assignments, governance events, promotion rule versions
- Fleet device last-known state, commands, config versions, rollouts
- Analytics event log + checkpoints (binary media never stored)

JSON files under `LEARNING_DATA_DIR` remain development compatibility only.

## Milestone 6A RAG Governance Persistence

Migration `0010_rag_governance_persistence.sql` establishes:

- `rag_documents` / `rag_document_versions` — ownership, lifecycle status, content_ref, embedding/chunk metadata
- `rag_publications` — atomic published pointer per document
- `rag_retrieval_traces` — query_ref + version/chunk attribution (no raw query text)
- `rag_rebuild_runs` — worker rebuild attempts and side_effect_id

Binary document bytes remain in object storage. JSON `rag_asset_versions.json` is development compatibility only.

## Milestone 5B Object Storage Metadata

Migration `0009_object_storage_metadata.sql` 建立 `object_storage_metadata`：

| Column | Purpose |
| --- | --- |
| `object_id` | Logical object id (tenant-prefixed) |
| `tenant_id` / `store_id` | Scope; store nullable for tenant-level assets |
| `content_type`, `size_bytes`, `checksum` | Integrity |
| `encryption`, `key_version` | Truthful crypto mode only |
| `provider`, `bucket`, `provider_key` | Adapter location |
| `retention_days`, `created_at`, `deleted_at` | Lifecycle |

Binary bytes 不寫入 PostgreSQL。Cloud S3/KMS wiring 屬外部依賴，見 Production Integration Milestone 10B。

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

### Milestone 1C Admin Identity Roll-forward

- Apply 0003 前執行 backup、migration validate 與 commercial scope integrity validation。
- 0003 只新增 table、constraint 與 index，不修改 0001/0002，也不刪除 legacy Admin token configuration。
- Application rollback 可暫時重新啟用 `ENABLE_LEGACY_ADMIN_TOKEN`；不得 drop identity table 或改寫 0003 checksum。
- Schema、assignment 或 session 問題以新的 forward migration修正。Permission catalog 可由 `python backend/scripts/manage_admin_identity.py sync-permissions` idempotently 同步。
- 建立首位管理者使用 `python backend/scripts/manage_admin_identity.py bootstrap --login <identity>`；password 由互動式 prompt 或 `ADMIN_BOOTSTRAP_PASSWORD` environment 提供，不放在 command history。
- 確認正式 session login、permission denial、audit 與 revoke 後，production 關閉 legacy flag。

### Milestone 1D Device Identity Roll-forward

- Apply 0004 前完成 backup、0001–0003 clean validation 與 device ownership盤點。
- 套用後先執行 `python backend/scripts/manage_admin_identity.py sync-permissions`，同步新增的 `device_identity.manage` machine name。
- 先對每台 active Kiosk issue credential，在受控 channel 完成一次性 exchange，驗證 `DevicePrincipal` scope 與 WebSocket/checkout smoke。
- Rotation 先建立 replacement，舊 credential 在 `DEVICE_CREDENTIAL_ROTATION_GRACE_SEC` 內可並行；cutover 確認後 revoke 舊 credential。
- Application rollback 可暫時明確啟用 `ENABLE_LEGACY_KIOSK_TOKEN`；不得 drop identity tables、保存 raw credential 或改寫 0004 checksum。
- Credential/session/event constraint 或資料問題使用新的 forward migration修正。

### Milestone 1E Scope Contract Roll-forward

- Apply 0005 前先執行 backup、migration clean validation 與 `validate_commercial_scope.py --require-complete`；任何 null/orphan/hierarchy mismatch 都先用新的 forward repair migration 處理。
- 0005 是 contract migration，不提供假的 down migration，也不得修改 0002–0004 checksum。
- Application rollback 可暫時回到 Default Scope compatibility adapter，但已收緊的 ownership column 不應放寬或刪除。
- 大型 production table 的 lock duration 必須先在 staging 以 production-like volume 演練；超出 maintenance budget 時拆成新的 expand/backfill/validate/contract migrations。

### Milestone 1F Member UUID / PII Roll-forward

- Apply 0006 前先完成 backup、0001–0005 clean validation、scope integrity validation，並確認部署可取得版本化 Member PII key material。
- 0006 將 Member primary key 切換為 UUID、保留 phone compatibility column，並 backfill preferences、sessions、orders 的 `member_id`；不修改任何既有 migration。
- Apply 後執行 `python backend/scripts/verify_member_identity_migration.py --backfill --require-clean`。輸出只含 violation type/count 與 updated count，不含 phone、ciphertext、key 或 connection string。
- 切換順序為 `legacy → dual → uuid_preferred → uuid_only`；每階段確認 lookup、dual-write drift、orphan reference、Admin masking、delete/anonymization 與 rollback 指標後才前進。
- Key rotation 先部署包含舊／新版本的 keyring，再切換 active version 並重跑 idempotent backfill；完成驗證前不得移除舊 decrypt key。
- Application rollback 可把 read mode 回到前一階段，但不得改回 phone primary key、改寫 0006 checksum或移除 UUID references；資料問題使用新的 forward migration 修正。
- External Secret Manager/KMS wiring 由部署環境負責；Repository 只提供 environment-backed contract，不宣稱未驗證的外部整合。法務與隱私審查仍是人工 Gate。

### Milestone 1G Order / Checkout Roll-forward

- Apply 0007 前先完成 backup、0001–0006 clean validation、scope/Member identity integrity validation，並確認 application 已使用 server-side pricing。
- 0007 只新增正式 `orders` aggregate、item/promotion snapshots、outcome 與 outbox，不刪除 legacy `member_orders` 或修改既有 migration。
- Cutover 前以 PostgreSQL 16 驗證同 request replay、fingerprint conflict、concurrent duplicate、transaction rollback、scope isolation、historical snapshot 與 cancellation outbox。
- Application rollback 可停止新 Order writer 並暫時維持 legacy checkout；不得 drop 0007 tables 或改寫 checksum。資料或 constraint 問題以新 forward migration 修正。
- Outbox 在 Worker 2E 前只保存發布意圖；不得手動標記 `published_at` 偽裝已送達，也不得把外部 provider call 放進 checkout transaction。

### Milestone 2E Worker / Outbox Roll-forward

- Apply 0008 前先完成 backup 與 0001–0007 clean validation。
- 0008 只新增 `background_jobs` 與 outbox claim/dead-letter 控制欄位，不修改 0007 checksum 或 checkout transaction 語意。
- Worker process（`backend/scripts/run_worker.py`）負責 claim、retry、dead-letter 與 outbox publish；API process 不得同步執行長工作。
- Application rollback 可停止 worker 並保留未發布 outbox；不得 drop 0008 tables 或改寫 checksum。資料問題使用新 forward migration 修正。

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
