# Backend Maintenance Scripts

`backend/scripts/` 保存 production-adjacent 的 migration、bootstrap、validation 與 worker CLI；demo/一次性工具仍放 Repository `tools/`。

## 腳本

| 腳本 | 用途 |
| --- | --- |
| `bootstrap_local_pilot.py` | 冪等建立單店 tenant/store/device 與 Admin；不列印密碼 |
| `manage_admin_identity.py` | trusted Admin/RBAC provisioning 與管理 |
| `prepare_local_persistence.py` | 建立互不重疊的本機 runtime 目錄與 `0600` PostgreSQL secret files |
| `manage_runtime_persistence.py` | persistence status、migration 與 rollback-only write probe |
| `manage_postgres_migrations.py` | legacy-compatible migration status/validate/apply 入口 |
| `verify_member_identity_migration.py` | Member UUID/PII backfill 與無 PII integrity check |
| `validate_commercial_scope.py` | tenant/store/device aggregate scope integrity |
| `import_rag_governance_json.py` | legacy RAG governance JSON → durable storage 的冪等匯入 |
| `validate_local_environment.py` | local-dev/postgres/full/pilot/test/ci profile 檢查；只印 PASS/WARN/FAIL |
| `validate_local_pilot_data_paths.py` | 確認 pilot 商業資料不落 JSON SoT |
| `validate_voice_turn_performance.py` | 以真實 device session 執行固定 30 回合 Voice Turn，驗證 durable event protocol 與 warm-state P95 |
| `run_worker.py` | bounded worker cycle，處理 background jobs 與 order outbox |

## 使用原則

從 `UI_API/` 執行，先看參數：

```bash
cd UI_API
python backend/scripts/manage_postgres_migrations.py --help
python backend/scripts/run_worker.py --help
python backend/scripts/validate_local_environment.py --list
```

- 寫入型腳本應預設 dry-run、需要明確 flag，或提供可觀察的冪等行為。
- 不把 secret、完整 PII、document content 或 production payload 印到 stdout/log。
- Worker 是獨立 process；不要把長期工作 loop 塞進 FastAPI request 或 lifespan。
- `pilot` 執行 migration/bootstrap 前先備份，並準備 roll-forward/recovery。
- PostgreSQL 備份工具的 major version 必須與 server 相同；本機 PostgreSQL 18 pilot 使用隔離安裝的 PostgreSQL 18 client，不以系統 PostgreSQL 16 client 建立可採信的 dump。
