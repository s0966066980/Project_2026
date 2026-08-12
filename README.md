# Project_2026 — Smart Ordering Kiosk

Project_2026 是以 Docker Compose 執行的單店智慧自助點餐系統。Kiosk、Admin、API 與 worker 使用同一個 FastAPI 應用邊界；PostgreSQL、local Ollama 與 R1-Omni 以獨立容器執行。

目前支援本機／LAN 開發與單店封閉式 Pilot 基礎驗證，尚未宣告 production certification。AI、語音與情緒服務故障時，基本菜單、購物車與訂單確認仍必須可用。

## 系統架構

```text
Browser
├── Kiosk  顧客點餐
└── Admin  門市管理
      │
      ▼
FastAPI application
├── /api/v1 HTTP API（唯一對外契約前綴）與 WebSocket
├── Ordering / Member / Campaign / RAG capabilities
├── Identity / RBAC / Operations settings
└── Health / diagnostics
      │
      ├── PostgreSQL
      ├── Durable worker / transactional outbox
      ├── Local Ollama
      └── R1-Omni
```

Docker 是唯一支援的 application runtime；不使用 Conda 或 host-native Python 作為驗證環境。

## 快速開始

第一次使用讓 setup script 完成全部工作：建立 `.env`、安裝並檢查 Docker、驗證本機模型、建置 image、拉取 Ollama 模型，最後啟動 stack 並等待健康檢查。以下指令都從 repository root 執行。

```bash
bash docker/scripts/setup.sh              # NVIDIA GPU（預設）
bash docker/scripts/setup.sh --cpu        # 無 GPU
```

已安裝 Docker 而不想讓 script 動主機套件時加上 `--no-install`。完成後 Kiosk 位於 <http://127.0.0.1:8000/kiosk>，Admin 位於 <http://127.0.0.1:8000/admin>。

R1-Omni 權重不會提交到 Git 或打包進 image，setup 也不會下載。預設路徑是 `R1-Omni/models/`；其他位置請在根目錄 `.env` 設定 `R1_MODELS_PATH`。權重目錄結構見 [docker/README.md](docker/README.md)。

## 日常操作

Compose stack 分成三層，所有指令都需要同一組 `-f` 參數：

| 檔案 | 內容 |
| --- | --- |
| `docker/compose.yaml` | PostgreSQL、migration、app、worker |
| `docker/compose.ai.yaml` | Ollama 與 CPU R1-Omni |
| `docker/compose.ai-gpu.yaml` | 可選的 NVIDIA GPU 覆蓋 |

把這組參數定義一次再重複使用。**啟動與關閉必須用完全相同的 overlay 組合**，用變數可以直接避免這個常見錯誤：

```bash
export COMPOSE="docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml"
export COMPOSE="$COMPOSE -f docker/compose.ai-gpu.yaml"   # 僅在使用 GPU 時追加
```

之後：

```bash
$COMPOSE build                 # 建置 image
$COMPOSE build --no-cache      # 強制重新下載依賴並重建 layer
$COMPOSE up -d --wait          # 啟動；先跑完 migration 再起 app / worker / ollama / r1-omni
$COMPOSE ps                    # 容器狀態
$COMPOSE logs -f app worker ollama
$COMPOSE down                  # 停止容器，保留 named volumes
```

健康檢查：

```bash
curl -fsS http://127.0.0.1:8000/live
curl -fsS http://127.0.0.1:8000/ready
```

只有確定要一併刪除資料庫、模型與 cache 時才使用：

```bash
$COMPOSE down --volumes --remove-orphans
```

### 直接使用 Docker CLI

`docker/Dockerfile` 的 build context 必須是 repository root，否則 `COPY docs/` 與其他 root-level source 會找不到。不要使用 `docker build -f docker/Dockerfile docker`：

```bash
docker build -f docker/Dockerfile --target runtime -t project-2026:local .
```

## 服務網址

Port 全部由根目錄 `.env` 決定，僅綁定 loopback。

| 服務 | 網址 | `.env` 變數（compose 預設） |
| --- | --- | --- |
| Kiosk | `http://127.0.0.1:8000/kiosk` | `BIND_ADDRESS` / `APP_PORT`（`127.0.0.1` / `8000`） |
| Admin | `http://127.0.0.1:8000/admin` | 同上 |
| HTTP API | `http://127.0.0.1:8000/api/v1/...` | 同上 |
| Liveness | `http://127.0.0.1:8000/live` | 同上 |
| Readiness | `http://127.0.0.1:8000/ready` | 同上 |
| Ollama | `http://127.0.0.1:${OLLAMA_PORT}` | `OLLAMA_PORT`（`11434`） |
| R1-Omni | `http://127.0.0.1:${R1_OMNI_PORT}` | `R1_OMNI_PORT`（`7890`） |

## 驗證

```bash
bash docker/scripts/test.sh       # 核心 Docker smoke test
bash docker/scripts/test-ai.sh    # AI image dependency smoke test
```

`test.sh` 會用獨立的 compose project 與 host port（預設 18000，可用 `SMOKE_APP_PORT` 覆寫），所以不需要先停掉正在跑的 stack。

Frontend：

```bash
cd UI_API/frontend
npm run syntax
npm run typecheck
npm test
npm run build
```

## 專案結構

```text
Project_2026/
├── docker/                 # Dockerfiles、Compose 與 setup/test scripts
├── UI_API/                 # capability backend、Admin/Kiosk、worker 與 tests
├── R1-Omni/                # 情緒模型服務；權重不入 Git
├── config/                 # 過渡設定、local profile 範例與 model registry
├── docs/adr/               # 架構決策紀錄
├── CONTEXT.md              # domain glossary
├── Project_2026_Execution_Plan.md
├── docs/upgrade/           # Commercial V1 路線與 gate 證據
├── scripts/backup/         # 備份、驗證與還原演練
└── tools/                  # 非 production 的一次性工具
```

## 備份與還原

```bash
bash scripts/backup/backup_postgres.sh        # 權威資料庫，附 schema/checksum manifest
bash scripts/backup/backup_objects.sh         # objects 與 RAG index
bash scripts/backup/verify_backup.sh --latest # checksum 與可讀性
bash scripts/backup/restore_test.sh --latest  # 還原到臨時資料庫並比對
```

備份預設寫到 `.backups/`（已 git-ignore，內含會員 PII）。`BACKUP_ROOT` 指向與主機分離的儲存才符合 Pilot Recovery Objective —— 這一步是操作者責任，repository 無法代為驗證。**有備份腳本不算完成，`restore_test.sh` 通過才算。**

## 目前限制

- Compose development/local profile 不等於 secured Pilot deployment。
- Pilot Configuration Authority、目標 Kiosk 實機與 provider/customer-evidence 授權尚未提供。
- Codex／Claude／Grok CLI 與其憑證依 owner 決定暫不實作；文字模型維持 local Ollama `LOCAL_ONLY` 路徑。
- Payment/POS 目前是 manual adapter。
- CI release attestation、production backup/restore、監控與回滾仍屬後續 Pilot readiness gates。

## 延伸文件

| 文件 | 內容 |
| --- | --- |
| [docker/README.md](docker/README.md) | Compose 分層、更新與除錯、安全邊界、Local Pilot 硬化流程 |
| [UI_API/README.md](UI_API/README.md) | 能力邊界、Admin/Kiosk 分工、maintenance CLI |
| [Project_2026_Execution_Plan.md](Project_2026_Execution_Plan.md) | 完成度與阻塞證據 |
| [docs/upgrade/](docs/upgrade/) | Commercial V1 升級路線與 gate 證據 |
| [CONTEXT.md](CONTEXT.md) | domain glossary |
| [docs/adr/](docs/adr/) | 架構決策紀錄 |
