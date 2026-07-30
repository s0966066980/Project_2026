# UI_API 核心應用

`UI_API/` 是 Project_2026 的 production path，包含 FastAPI、Kiosk、Admin、資料存取、可靠 worker 與 RAG/AI integrations。

部署目標是單店 local pilot；目前尚未 production certified。

## 功能範圍

- Kiosk：菜單、購物車、會員、推薦、活動 banner、語音/情緒輔助、互動介入、checkout。
- Admin：登入/RBAC、設定、會員、供應、活動、推薦事件、RAG、健康與 AI 測試。
- Backend：legacy `/api/*`、typed `/api/v1/*`、WebSocket、Admin/Device identity、commercial scope、audit/observability。
- Data：Runtime Persistence Profile、PostgreSQL 18 單機路徑、隔離的 SQLite 測試 adapter、Redis shared infrastructure、local/S3 object-storage contract；JSON 不再是 runtime adapter。
- Async：獨立 worker 處理 durable jobs 與 order outbox；AI/provider 失敗不得阻擋 checkout。

## 結構

```text
UI_API/
├── main.py                    # FastAPI app 與本機 server 入口
├── config.py                  # 環境、動態設定與 commercial fail-closed 驗證
├── backend/
│   ├── app_factory.py         # middleware、health、static、route 組裝
│   ├── api/                   # route registry、v1 contracts/error envelope
│   ├── bootstrap/             # startup、process、server、module registry
│   ├── modules/identity/      # 已抽離的 Identity Application API
│   ├── routes/                # HTTP/WebSocket transport
│   ├── services/              # 既有 workflows 與 compatibility shims
│   ├── repositories/          # PostgreSQL/Redis persistence adapters
│   ├── integrations/          # manual Payment/POS adapters
│   ├── schemas/               # PostgreSQL migrations 0001–0021
│   └── scripts/               # migration、pilot、worker、validation CLI
├── frontend/                  # Kiosk、Admin、shared clients/UI
├── menu_data/                 # 菜單來源
├── rag_documents/             # 可審核與重建的 RAG 原始來源
├── learning_data/             # local runtime compatibility data
├── tests/                     # Backend/architecture/integration tests
└── requirements.txt           # 完整 local runtime dependencies
```

## 執行路徑

```text
main.py → app_factory.create_app()
        → api.router.register_routes()
        → api.route_registry → routes/*
        → module Application API 或既有 service
        → repository / integration
```

`main.py` 的本機 server 可讓同一 app 綁定 `APP_PORT` 與 `ADMIN_PORT`。`/live` 只表示 process 存活；`/ready` 會回報 dependency readiness。AI/STT/TTS/RAG 在 lifespan 背景初始化，失敗只降級相關能力。

可靠工作另以 process 啟動：

```bash
cd UI_API
python backend/scripts/run_worker.py --help
```

## 啟動

核心應用：

```bash
cd UI_API
source /home/oliver/anaconda3/etc/profile.d/conda.sh
conda activate emotion_ui
ENABLE_NGROK=false python main.py
```

local pilot 設定先從 Repository 根目錄的 `config/profiles/local-pilot.env.example` 建立部署擁有的環境檔，再執行：

```bash
cd UI_API
python backend/scripts/validate_local_environment.py --profile local-pilot
```

目前資料庫目標是本機單一主機，不是 HA：

```bash
cd UI_API
uv run python backend/scripts/prepare_local_persistence.py --refresh-database-urls
docker compose -f deploy/postgres/compose.yaml up -d
uv run python backend/scripts/manage_runtime_persistence.py migrate
uv run python backend/scripts/manage_runtime_persistence.py status
uv run python backend/scripts/manage_runtime_persistence.py write-probe
```

`RUNTIME_DATA_ROOT` 下的 PostgreSQL、備份、物件、RAG 索引、SQLite、日誌、匯入匯出與暫存目錄互不重疊且預設為 `0700`。PostgreSQL 容器只掛載 `postgres/pgdata` 與 `postgres/wal-archive`。完整存取矩陣與未來三 VM／三可用區契約見 [ADR 0010](../docs/adr/0010-adopt-local-single-host-postgresql-runtime.md)。
容器對主機只綁定 `127.0.0.1:55432`，避免干擾主機既有的 5432 PostgreSQL；容器內仍使用標準 5432。

模型整合啟動方式見 [Repository README](../README.md#本機啟動)。

## 邊界與限制

- 現況是 Transitional Modular Monolith；Identity 已抽離，其餘多數 domain 尚在 `routes/services/repositories`。
- `services/admin_identity_service.py` 等檔案是相容 shim，不新增業務責任。
- `/api/v1` 已有 typed read/write contracts，但 `v1_routes.py` 仍直接依賴多個 service/repository。
- `staging`、`pilot`、`production` 必須以 PostgreSQL 為商業資料 Source of Truth，並在啟動時 fail closed。
- 本機 `DATABASE_TOPOLOGY=single` 不構成 production readiness；production 必須使用可觀測到同步與非同步 standby 的 `ha` 拓撲。
- Payment/POS 目前只有 manual adapter；manual pending 不代表已自動扣款或送單。
- 大型模型不是核心 API 的必要條件。
