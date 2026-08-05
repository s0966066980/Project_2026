# Project_2026 — Smart Ordering Kiosk

Project_2026 是單店本地端 / LAN 的智慧自助點餐系統。主要應用位於 `UI_API/`，提供 Kiosk、Admin、會員、推薦、RAG、語音、R1-Omni 情緒分析與結帳流程；R1-Omni 為唯一情緒模型服務，不應阻擋核心點餐與結帳。

目前部署階段是 **local pilot / NOT_READY**；Payment 與 POS 只有 manual adapter，尚未通過 production certification。

> 架構狀態：**Transitional Modular Monolith（模組化單體過渡期）**。目前同時存在既有的 `routes → services → repositories` 分層，以及逐步抽離中的 `modules/<domain>` 公開 Application API。文件會區分「目前實作」與「目標邊界」，避免把尚未完成的重構視為既成事實。

## 目前能力

- **Kiosk**：菜單、購物車、會員、推薦、活動廣告、語音協助、互動障礙偵測、結帳。
- **Admin**：登入與權限、設定、會員、供應狀態、活動、推薦事件、RAG、健康檢查。
- **Backend**：FastAPI、HTTP / WebSocket、Admin/Device identity、RBAC、健康檢查、結構化 logging，以及由 Runtime Persistence Profile 管理的 PostgreSQL 路徑。
- **資料與非同步工作**：21 個 forward PostgreSQL migrations、隔離的 SQLite 測試 adapter、Redis shared rate-limit/cache/lock、可靠 worker、transactional outbox、local/S3 object-storage contract；JSON 不是 runtime persistence adapter。
- **AI**：Ollama（本機）、NVIDIA NIM（雲端）、R1-Omni、STT / TTS；外部 AI 呼叫集中於 adapter，失敗時不得破壞核心交易流程。

## 專案結構

```text
Project_2026/
├── UI_API/                         # 主要產品程式
│   ├── main.py                     # FastAPI 執行入口
│   ├── config.py                   # 環境變數與 runtime settings
│   ├── backend/
│   │   ├── app_factory.py          # App、middleware、health、route 註冊
│   │   ├── api/                    # Route registry、v1 contracts、API 組裝
│   │   ├── modules/                # 新模組邊界；目前 Identity 已開始抽離
│   │   ├── routes/                 # HTTP / WebSocket transport
│   │   ├── services/               # 既有 application workflow 與相容層
│   │   ├── repositories/           # PostgreSQL / Redis 資料存取
│   │   ├── integrations/           # Payment、POS、AI / 外部 provider adapters
│   │   ├── schemas/                # Schema、migration、跨層資料結構
│   │   ├── realtime/               # WebSocket 與事件推送
│   │   └── bootstrap/              # 啟動與 process helper
│   ├── frontend/
│   │   ├── kiosk/                  # 顧客點餐端
│   │   ├── admin/                  # 門市後台
│   │   └── shared/                 # 通用 API / HTTP / realtime / UI primitives
│   ├── tests/                      # Backend、security、migration、integration tests
│   ├── menu_data/                  # 菜單資料
│   ├── rag_documents/              # RAG 原始文件
│   └── learning_data/              # Local runtime data
├── R1-Omni/                        # 唯一多模態情緒模型服務
├── scripts/                        # 本機模型與 UI_API 啟動腳本
├── config/profiles/                # local-pilot 環境範例
└── tools/                          # Demo、維運或一次性工具；非 production path
```

## Runtime 與請求路徑

### Backend 啟動

```text
UI_API/main.py
  → backend/app_factory.py:create_app()
    → backend/api/router.py:register_routes()
      → backend/api/route_registry.py
        → backend/routes/*
```

`app_factory.py` 負責 CORS、安全 header、request / trace ID、`/live`、`/ready`、靜態資源與 route 註冊。開發、測試與 debug routes 由 feature flags 控制，商用環境必須 fail closed。

需要可靠重試的工作不在 API lifespan 內常駐消費，而由 `backend/scripts/run_worker.py` 啟動獨立 process，處理 `background_jobs` 與 `order_outbox`。

### Backend 現況與目標

目前有兩條並存路徑：

```text
既有相容路徑
Route → Service → Repository → PostgreSQL

目標模組路徑
Route → modules/<domain>/application.py
      → Domain / Port
      → Adapter / Integration
```

Identity 已移至 `backend/modules/identity`，但既有 route 仍可經 `services/admin_identity_service.py` 等相容 shim 呼叫。`/api/v1` 已提供 typed read/write contracts、統一 envelope 與權限檢查，但 `v1_routes.py` 還直接依賴多個 service / repository；`bootstrap/module_registry.py` 中其他 domain router 也仍是待切換候選，因此模組化尚未完成。

新功能應遵守：

1. Route 只處理 HTTP、authentication / authorization、validation 與 response mapping。
2. 業務規則放在 module Application API 或 service，不在 route 直接讀寫資料。
3. Repository / adapter 負責 I/O；不得反向依賴 route。
4. 新模組只透過其他模組的公開 Application API 或事件互動，不直接 import 對方的 repository / adapter。
5. Ollama、NVIDIA NIM、Emotion、Payment、POS 等外部呼叫集中於 integration / adapter。
6. `pilot`、`staging`、`production` 必須使用 PostgreSQL，禁止資料庫失敗後靜默 fallback 到 JSON。
7. AI、RAG、語音與情緒分析不得成為 checkout 的必要條件。

目前資料與整合邊界：

- 目前部署目標是本機單一主機的 PostgreSQL 18，資料庫只綁定 loopback；`staging` / `pilot` / `production` 啟動時會檢查 PostgreSQL、安全設定與 commercial scope。
- PostgreSQL migrations `0001`–`0021` 涵蓋會員、tenant/store/device scope、Admin RBAC、Order/outbox、worker、object metadata、RAG governance，以及已抽離的 domain durable records。
- `RUNTIME_DATA_ROOT` 將 PostgreSQL、備份、物件、RAG 索引、SQLite、日誌、匯入匯出與暫存資料完全分目錄；PostgreSQL 容器只取得其資料與 WAL 目錄。未來 production 才部署 primary、同步 standby、非同步 standby 至三台 VM／三個可用區，詳見 [ADR 0010](docs/adr/0010-adopt-local-single-host-postgresql-runtime.md)。
- Redis 是 shared cache、rate limit 與 lock adapter；未設定時只允許非商用相容路徑。
- Payment/POS 目前只有 manual adapter；不應把 pending manual result 描述成自動付款完成或 POS 已送單。

### Frontend 邊界

- `frontend/kiosk/`：顧客點餐流程、畫面狀態與 kiosk controllers。
- `frontend/admin/`：營運與維運流程；目前已拆出部分 `modules/` 與 `features/`，但 `admin.js` 仍是大型頁面 orchestrator。
- `frontend/shared/`：只放真正共用的 API、HTTP、realtime、hook、UI primitive 與 design token；不得放 Kiosk 或 Admin 專屬 business state。
- Kiosk 與 Admin 不互相 import。
- 新 API 呼叫應集中至 client，不新增散落的 `fetch()`；既有 legacy `/api/*` 與 typed `/api/v1/*` 需漸進收斂，不做 Big Bang rewrite。
- 價格、promotion eligibility、訂單狀態、會員 scope、付款結果與權限判斷以 server 為準。

## Docker 可攜式部署

完整的建置、權重下載、模型快取、CPU／GPU 啟動與驗證流程請見 [docker/README.md](docker/README.md)。

在已準備好 R1-Omni 本地權重的 Debian/Ubuntu 主機，首次部署可直接執行 `bash docker/scripts/setup.sh`；GPU 主機使用 `bash docker/scripts/setup.sh --gpu`。腳本會安裝 Docker/Compose、建立 `.env`、建置並啟動服務，但不會下載模型權重。

此版本可在支援 Docker Compose 的 Linux、macOS 與 Windows（Docker Desktop）執行。核心點餐系統使用可攜式 CPU 映像；大型語言模型、R1-Omni、語音與 RAG 則由 AI Compose overlay 完整封裝。實際可使用的模型大小仍取決於裝置的 CPU 架構、RAM／VRAM 與磁碟空間。

Docker stack 只使用專案根目錄的 `.env`；手動執行 Compose 時一律加上
`--env-file .env`。`UI_API/.env` 是原生 `emotion_ui` 啟動用的另一個設定檔，
不要拿來替代 Docker 的 `.env`。

### 快速啟動

只在本機使用時，可直接啟動：

```bash
docker compose --env-file .env -f docker/compose.yaml up --build -d --wait
```

若要自訂連接埠、資料庫密碼或管理員密碼，先建立環境檔：

```bash
cp docker/.env.example .env
```

修改 `.env` 內兩個密碼後再啟動。預設只綁定 `127.0.0.1`；需要讓同一個可信任 LAN 的其他裝置連線時，才將 `BIND_ADDRESS` 改成 `0.0.0.0`，並務必使用高強度密碼。

啟動後使用同一個連接埠：

```text
Kiosk: http://127.0.0.1:8000/kiosk
Admin: http://127.0.0.1:8000/admin
Live:  http://127.0.0.1:8000/live
Ready: http://127.0.0.1:8000/ready
```

部署包含：

- `postgres`：PostgreSQL 18，資料保存在 Docker named volume。
- `migrate`：啟動時執行 forward migrations，成功後結束。
- `app`：FastAPI、Kiosk 與 Admin。
- `worker`：可靠背景工作與 outbox 處理程序。

常用維運指令：

```bash
docker compose --env-file .env -f docker/compose.yaml ps
docker compose --env-file .env -f docker/compose.yaml logs -f app worker
docker compose --env-file .env -f docker/compose.yaml down
```

`docker compose down` 會保留資料；只有明確執行 `docker compose down --volumes` 才會刪除 PostgreSQL 與應用資料。

### 完整 AI 版本

完整版本包含 Ollama 大型語言模型、R1-Omni 多模態情緒服務、faster-whisper 語音辨識、Edge TTS、ChromaDB／FastEmbed RAG，以及共享的模型與媒體 volumes。Compose **不會自動下載 Ollama 或 R1-Omni 權重**；模型由使用者準備，容器只負責載入。

第一次使用依序執行：

```bash
cp docker/.env.example .env
```

1. 將 R1-Omni 所需的 Hugging Face repositories 下載至 `.env` 的 `R1_MODELS_PATH`。預設目錄必須是：

```text
R1-Omni/models/
├── R1-Omni-0.5B/              # StarJiaxing/R1-Omni-0.5B
├── bert-base-uncased/          # google-bert/bert-base-uncased
├── siglip-base-patch16-224/    # google/siglip-base-patch16-224
└── whisper-large-v3/           # openai/whisper-large-v3
```

下載工具不限，但必須保留每個 repository 的完整檔案結構；不要把權重放進 image。Compose 會將這個目錄唯讀掛載到 `/models`，缺檔時 R1-Omni 會直接列出缺少的路徑。

2. 只啟動 Ollama，然後手動下載 `.env` 中選擇的模型：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml up -d ollama
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml exec ollama ollama pull qwen3.5:4b
```

若你修改了 `OLLAMA_MODEL`，第二個指令也要使用相同名稱。模型會保留在 `ollama_models` named volume；後續 `docker compose down` 不會刪除它。

3. 啟動完整 CPU stack：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml up --build -d --wait
```

有 NVIDIA GPU 的 Linux 主機應先安裝 NVIDIA driver；Debian/Ubuntu 可直接使用 `bash docker/scripts/setup.sh --gpu` 自動安裝並設定 NVIDIA Container Toolkit。手動使用 Compose 時，需先完成 toolkit 設定，再於第 3 步加上 GPU overlay：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  up --build -d --wait
```

4. 驗證服務與已安裝的 Ollama 模型：

```bash
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml ps
docker compose --env-file .env -f docker/compose.yaml -f docker/compose.ai.yaml exec ollama ollama list
curl -fsS http://127.0.0.1:7890/health
curl -fsS http://127.0.0.1:8000/ready
```

預設 Ollama 模型為 `qwen3.5:4b`，可在 `.env` 用 `OLLAMA_MODEL` 調整。faster-whisper 與 FastEmbed 仍使用 `ai_cache` named volume；第一次實際啟用相關功能時，由其 runtime 管理快取。CPU 模式主要用於相容性與功能驗證，R1-Omni 和大型模型在 CPU 上可能很慢。Edge TTS 需要網路。服務預設只綁定 loopback；若要從其他可信任裝置存取，才將 `BIND_ADDRESS=0.0.0.0`。

### Docker 驗證

以下腳本會建置 runtime/test 映像、執行完整容器測試、建立全新的暫存 PostgreSQL、套用 migrations、啟動所有服務，並驗證 readiness、Kiosk 與 Admin；完成後會清除專用測試容器與 volumes：

```bash
docker/scripts/test.sh
docker/scripts/test-ai.sh
```

第一個腳本驗證核心 stack 與 PostgreSQL migrations；第二個腳本只建置完整 AI 映像並驗證 Compose 設定及語音、RAG、R1-Omni runtime imports，**不下載或載入模型權重**。權重與 GPU 實機推論由使用者依上方流程另外驗證。

此 Compose 預設為可攜式 development/local 模式，Payment 與 POS 仍是 manual adapter，不代表 production certification。

## 安裝

### Backend

UI_API 的本機 Python 執行環境統一為 Conda `emotion_ui`（Python 3.10）：

```bash
source /home/oliver/anaconda3/etc/profile.d/conda.sh
conda activate emotion_ui
python -m pip install -U pip
pip install -r UI_API/requirements.txt
```

`UI_API/requirements.txt` 目前同時包含 Web、RAG、語音與模型相關重依賴。只做文件或前端修改時，不要為了單一檢查重裝全部 AI 套件。

### Frontend

```bash
cd UI_API/frontend
npm ci --ignore-scripts
```

## 本機啟動

### UI_API 單獨啟動

```bash
source /home/oliver/anaconda3/etc/profile.d/conda.sh
conda activate emotion_ui
cd UI_API
ENABLE_NGROK=false python main.py
```

建議使用 `bash scripts/start_r1_omni.sh`；腳本會明確啟用 `emotion_ui`，並在啟動前檢查 `faster_whisper`、`fastembed` 與 `edge_tts`。不要使用環境不明的 shell Python 或專案 `.venv` 啟動 UI_API。

預設網址：

```text
Kiosk: http://127.0.0.1:8000/kiosk
Admin: http://127.0.0.1:8001/admin
Live:  http://127.0.0.1:8000/live
Ready: http://127.0.0.1:8000/ready
```

`main.py` 會在 `APP_PORT` 與 `ADMIN_PORT` 啟動相同 FastAPI app；若兩者相同只會啟動一次。local pilot 的環境設定範例位於 `config/profiles/local-pilot.env.example`。

### 搭配 R1-Omni

```bash
UI_PY="$(command -v python)" \
R1_PY="/path/to/r1-omni-python" \
bash scripts/start_r1_omni.sh
```

兩個啟動腳本目前帶有開發機的預設 Python 路徑；其他機器請明確設定 `UI_PY`、`LLAMA_PY` 或 `R1_PY`。腳本模式預設使用 Kiosk `9000`、Admin `9001`。
