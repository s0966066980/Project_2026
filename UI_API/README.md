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
├── requirements-docker.txt    # Container core runtime dependencies
└── requirements-ai.txt        # Container AI runtime dependencies
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

可靠工作由 Compose 的獨立 `worker` service 啟動：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  logs -f worker
```

## 啟動

Project runtime 只支援 Docker。從 Repository 根目錄一鍵啟動 GPU stack：

```bash
bash docker/scripts/setup.sh
```

CPU 相容模式：

```bash
bash docker/scripts/setup.sh --cpu
```

setup 會建立根目錄 `.env`、建置 app/worker/R1 images、準備 Ollama 模型、執行 migrations 並等待完整 stack 健康。UI_API source 會被複製進 image；修改程式後需重新 build：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

目前 development Compose 使用 named volumes 保存 PostgreSQL、app data、Ollama models 與 AI cache。`docker compose down` 會保留資料；`down --volumes` 會刪除它們。

完整安裝、R1 權重位置與 CPU/GPU 操作見 [Repository README](../README.md#一鍵安裝與啟動) 與 [Docker README](../docker/README.md)。Pilot 的外部設定、備份與安全 profile 仍屬後續 readiness gate。

## 邊界與限制

- 現況是 Transitional Modular Monolith；Identity 已抽離，其餘多數 domain 尚在 `routes/services/repositories`。
- `services/admin_identity_service.py` 等檔案是相容 shim，不新增業務責任。
- `/api/v1` 已有 typed read/write contracts，但 `v1_routes.py` 仍直接依賴多個 service/repository。
- `staging`、`pilot`、`production` 必須以 PostgreSQL 為商業資料 Source of Truth，並在啟動時 fail closed。
- 本機 `DATABASE_TOPOLOGY=single` 不構成 production readiness；production 必須使用可觀測到同步與非同步 standby 的 `ha` 拓撲。
- Payment/POS 目前只有 manual adapter；manual pending 不代表已自動扣款或送單。
- 大型模型不是核心 API 的必要條件。
