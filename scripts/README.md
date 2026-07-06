# scripts 模組說明

`scripts/` 存放本機啟動與資料庫維運腳本。

## 主要腳本

| 腳本 | 用途 |
| --- | --- |
| `start_emotion_llama.sh` | 啟動 UI_API、Ollama、Emotion-LLaMA 與 PostgreSQL 準備流程。 |
| `start_r1_omni.sh` | 啟動 UI_API、Ollama、R1-Omni 與 PostgreSQL 準備流程。 |
| `lib_postgres.sh` | PostgreSQL 初始化、migration 與連線檢查 helper。 |
| `backup_postgres.sh` | PostgreSQL 備份。 |
| `restore_postgres.sh` | PostgreSQL 還原。 |

## 使用方式

```bash
bash scripts/start_emotion_llama.sh
bash scripts/start_r1_omni.sh
bash scripts/backup_postgres.sh
bash scripts/restore_postgres.sh backups/postgres/<dump-file>.dump
```

## 常用環境變數

| 變數 | 用途 |
| --- | --- |
| `UI_PY` | UI_API Python interpreter |
| `LLAMA_PY` | Emotion-LLaMA Python interpreter |
| `R1_PY` | R1-Omni Python interpreter |
| `OLLAMA_BIN` | Ollama executable |
| `MODEL_NAME` | Ollama 模型 |
| `APP_PORT` | Kiosk / API port |
| `ADMIN_PORT` | Admin port |
| `OPEN_BROWSER` | 是否自動開啟瀏覽器 |
| `POSTGRES_ENABLED` | 是否處理 PostgreSQL |

## 維護規則

- 啟動腳本只負責本機 orchestration。
- 商用部署應改用 systemd、Docker Compose 或正式 process manager。
- 腳本變更後需執行 `bash -n scripts/*.sh`。
