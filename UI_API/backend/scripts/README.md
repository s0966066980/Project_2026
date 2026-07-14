# Backend Maintenance Scripts

`backend/scripts/` 保存 production-adjacent 的 migration、bootstrap、validation 與 worker CLI；demo/一次性工具仍放 Repository `tools/`。

> 實作盤點：2026-07-14。

## 腳本

| 腳本 | 用途 |
| --- | --- |
| `bootstrap_local_pilot.py` | 冪等建立單店 tenant/store/device 與 Admin；不列印密碼 |
| `manage_admin_identity.py` | trusted Admin/RBAC provisioning 與管理 |
| `manage_postgres_migrations.py` | migration status/validate/apply |
| `migrate_member_storage.py` | JSON member/recommendation data → PostgreSQL；預設 dry-run |
| `validate_member_postgres_migration.py` | 驗證 legacy member migration 結果 |
| `verify_member_identity_migration.py` | Member UUID/PII backfill 與無 PII integrity check |
| `validate_commercial_scope.py` | tenant/store/device aggregate scope integrity |
| `import_rag_governance_json.py` | legacy RAG governance JSON → durable storage 的冪等匯入 |
| `validate_local_environment.py` | local-dev/postgres/full/pilot/test/ci profile 檢查；只印 PASS/WARN/FAIL |
| `validate_local_pilot_data_paths.py` | 確認 pilot 商業資料不落 JSON SoT |
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
- 新正式資料流程需補 target test/smoke、失敗恢復與 operator 說明。
- Worker 是獨立 process；不要把長期工作 loop 塞進 FastAPI request 或 lifespan。
- `pilot` 執行 migration/bootstrap 前先備份，並準備 roll-forward/recovery。
