# Project_2026 — Smart Ordering Kiosk

Project_2026 是單店本地端 / LAN 的智慧自助點餐系統。主要應用位於 `UI_API/`，提供 Kiosk、Admin、會員、推薦、RAG、語音、情緒分析與結帳流程；`Emotion-LLaMA/`、`R1-Omni/` 為可選模型服務，不應阻擋核心點餐與結帳。

目前部署階段是 **local pilot / NOT_READY**；Payment 與 POS 只有 manual adapter，尚未通過 production certification。

> 架構狀態：**Transitional Modular Monolith（模組化單體過渡期）**。目前同時存在既有的 `routes → services → repositories` 分層，以及逐步抽離中的 `modules/<domain>` 公開 Application API。文件會區分「目前實作」與「目標邊界」，避免把尚未完成的重構視為既成事實。

## 目前能力

- **Kiosk**：菜單、購物車、會員、推薦、活動廣告、語音協助、互動障礙偵測、結帳。
- **Admin**：登入與權限、設定、會員、供應狀態、活動、推薦事件、RAG、健康檢查。
- **Backend**：FastAPI、HTTP / WebSocket、Admin/Device identity、RBAC、健康檢查、結構化 logging、JSON 相容儲存與 PostgreSQL 商用路徑。
- **資料與非同步工作**：11 個 forward PostgreSQL migrations、Redis shared rate-limit/cache/lock、可靠 worker、transactional outbox、local/S3 object-storage contract。
- **AI**：Ollama、Gemini、Emotion-LLaMA、R1-Omni、STT / TTS；AI provider 必須保持可替換，失敗時不得破壞核心交易流程。

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
│   │   ├── repositories/           # JSON / PostgreSQL 資料存取
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
├── Emotion-LLaMA/                  # 可選情緒模型服務
├── R1-Omni/                        # 可選多模態模型服務
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
Route → Service → Repository → JSON / PostgreSQL

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
5. Ollama、Gemini、Emotion、Payment、POS 等外部呼叫集中於 integration / adapter。
6. `pilot`、`staging`、`production` 必須使用 PostgreSQL，禁止資料庫失敗後靜默 fallback 到 JSON。
7. AI、RAG、語音與情緒分析不得成為 checkout 的必要條件。

目前資料與整合邊界：

- `development` / `test` 可使用 JSON compatibility storage；`staging` / `pilot` / `production` 啟動時會檢查 PostgreSQL、安全設定與 commercial scope。
- PostgreSQL migrations `0001`–`0011` 涵蓋會員、tenant/store/device scope、Admin RBAC、Order/outbox、worker、object metadata、RAG governance，以及 recommendation/fleet/analytics control plane。
- Redis 是 shared cache、rate limit 與 lock adapter；未設定時只允許非商用相容路徑。
- Payment/POS 目前只有 manual adapter；不應把 pending manual result 描述成自動付款完成或 POS 已送單。

### Frontend 邊界

- `frontend/kiosk/`：顧客點餐流程、畫面狀態與 kiosk controllers。
- `frontend/admin/`：營運與維運流程；目前已拆出部分 `modules/` 與 `features/`，但 `admin.js` 仍是大型頁面 orchestrator。
- `frontend/shared/`：只放真正共用的 API、HTTP、realtime、hook、UI primitive 與 design token；不得放 Kiosk 或 Admin 專屬 business state。
- Kiosk 與 Admin 不互相 import。
- 新 API 呼叫應集中至 client，不新增散落的 `fetch()`；既有 legacy `/api/*` 與 typed `/api/v1/*` 需漸進收斂，不做 Big Bang rewrite。
- 價格、promotion eligibility、訂單狀態、會員 scope、付款結果與權限判斷以 server 為準。

## 安裝

### Backend

建議 Python 3.10 或 3.12：

```bash
python -m venv .venv
source .venv/bin/activate
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
cd UI_API
ENABLE_NGROK=false python main.py
```

預設網址：

```text
Kiosk: http://127.0.0.1:8000/kiosk
Admin: http://127.0.0.1:8001/admin
Live:  http://127.0.0.1:8000/live
Ready: http://127.0.0.1:8000/ready
```

`main.py` 會在 `APP_PORT` 與 `ADMIN_PORT` 啟動相同 FastAPI app；若兩者相同只會啟動一次。local pilot 的環境設定範例位於 `config/profiles/local-pilot.env.example`。

### 搭配 Emotion-LLaMA

```bash
UI_PY="$(command -v python)" \
LLAMA_PY="/path/to/emotion-llama-python" \
bash scripts/start_emotion_llama.sh
```

### 搭配 R1-Omni

```bash
UI_PY="$(command -v python)" \
R1_PY="/path/to/r1-omni-python" \
bash scripts/start_r1_omni.sh
```

兩個啟動腳本目前帶有開發機的預設 Python 路徑；其他機器請明確設定 `UI_PY`、`LLAMA_PY` 或 `R1_PY`。腳本模式預設使用 Kiosk `9000`、Admin `9001`。
