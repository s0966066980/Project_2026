# Scripts

`scripts/` 保存本機啟動與 PostgreSQL 維運腳本。這些腳本是 development/demo orchestration，不是長期 production process manager。

## 主要腳本

| 腳本 | 用途 |
| --- | --- |
| `start_emotion_llama.sh` | 準備 PostgreSQL，啟動 Ollama、Emotion-LLaMA 與 UI_API |
| `start_r1_omni.sh` | 準備 PostgreSQL，啟動 Ollama、R1-Omni 與 UI_API |
| `lib_postgres.sh` | PostgreSQL 初始化、migration 與連線 helper |
| `backup_postgres.sh` | 建立 PostgreSQL backup |
| `restore_postgres.sh` | 還原指定 backup |
| `pre_deploy_check.sh` | 發布前 backup、migration clean、scope、config fail-fast |
| `post_deploy_smoke.sh` | 發布後 `/live` `/ready` smoke |
| `record_restore_drill.sh` | 記錄隔離 restore drill 證據 |

## 使用

```bash
bash scripts/start_emotion_llama.sh
bash scripts/start_r1_omni.sh

bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh backups/postgres/<dump-file>.dump

bash scripts/pre_deploy_check.sh
bash scripts/post_deploy_smoke.sh
bash scripts/record_restore_drill.sh
```

Deployment contract 與 process 邊界見 [`docs/operations/DEPLOYMENT.md`](../docs/operations/DEPLOYMENT.md)。

Production apply、backup verification、隔離 restore 與 roll-forward 程序見 [`docs/POSTGRESQL_MIGRATIONS.md`](../docs/POSTGRESQL_MIGRATIONS.md)。

環境變數以 `.env.example` 與腳本內容為準，常用項目：

- `UI_PY`
- `LLAMA_PY`
- `R1_PY`
- `OLLAMA_BIN`
- `MODEL_NAME`
- `APP_HOST` / `APP_PORT` / `ADMIN_PORT`
- `OPEN_BROWSER`
- `POSTGRES_ENABLED`
- `POSTGRES_*`

## 維護規則

- 使用 `set -euo pipefail` 或等價的明確錯誤處理（與既有腳本相容時）。
- 所有路徑、Port、Interpreter 與 credential 可由環境設定，不硬編 production Secret。
- 啟動的 child process 需在 Ctrl-C/失敗時正確清理。
- 不以 `killall`/廣泛 process name 終止無關程序。
- Backup/restore 操作需明確顯示目標，避免意外覆寫。
- Production 應使用 Docker Compose、systemd、Kubernetes 或正式 process manager，並搭配 readiness、restart policy、log 與 Secret 管理。

## 驗證

只需檢查受影響腳本；完整基線：

```bash
bash -n scripts/start_emotion_llama.sh
bash -n scripts/start_r1_omni.sh
bash -n scripts/lib_postgres.sh
bash -n scripts/backup_postgres.sh
bash -n scripts/restore_postgres.sh
bash -n scripts/pre_deploy_check.sh
bash -n scripts/post_deploy_smoke.sh
bash -n scripts/record_restore_drill.sh
```
