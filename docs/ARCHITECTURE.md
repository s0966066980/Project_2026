# Project_2026 架構

- 文件版本：1.0
- 狀態：Active
- 最後更新：2026-07-13
- 架構策略：Modular Monolith First

## 1. 系統目的

Project_2026 提供自助點餐、營運後台、會員個人化、推薦、語音互動、RAG 與情緒分析。架構目標是在不破壞現有 Kiosk/Admin 流程的前提下，逐步具備多門市、可測試、可部署、可觀測與可治理能力。

## 2. 目前架構

```text
Browser
├── /kiosk ───────────────┐
└── /admin ───────────────┤
                          ▼
                 FastAPI UI_API
                 ├── routes
                 ├── services
                 ├── repositories
                 ├── WebSocket / event bus
                 ├── static frontend
                 ├── JSON compatibility storage
                 └── PostgreSQL optional storage
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
     Ollama/Gemini   Emotion-LLaMA      R1-Omni
```

現況優點：

- 已形成 `routes → services → repositories` 分層。
- Kiosk、Admin 與 shared frontend 已分目錄。
- 會員、推薦事件、供應狀態與 audit 已有 PostgreSQL 路徑。
- 已具 production route boundary、security headers、request ID、健康檢查與 CI 基線。
- AI provider 已可切換，適合逐步抽成 Port/Adapter。

目前限制：

- FastAPI 同時承擔 API、WebSocket、靜態前端與部分 background initialization。
- `config.py` 同時包含 infrastructure 與 runtime business settings。
- Admin/Kiosk 驗證仍以相容性 Token 為主，尚未建立完整 user/RBAC/device identity。
- 資料模型尚未完整具備 `tenant_id`、`store_id`、`device_id`。
- 部分前端協調器與樣式檔仍偏大。
- Rate limit、cache 與 background work 尚未形成分散式基礎設施。

## 3. 目標執行邊界

```text
Kiosk Web ───────────────┐
                         │ HTTPS / WebSocket
Admin Web ───────────────┤
                         ▼
             FastAPI Modular Monolith
             ├── identity / tenant / store / device
             ├── catalog / availability
             ├── order / checkout
             ├── member / promotion
             ├── recommendation / interaction
             ├── rag / admin / observability
             └── provider ports
                 │
        ┌────────┼─────────┐
        ▼        ▼         ▼
   PostgreSQL   Redis     Worker
                           │
                    ┌──────┴──────┐
                    ▼             ▼
               LLM Gateway   Emotion Gateway
```

目標不是立即建立大量 Microservices，而是先讓 domain boundary、contract、資料 ownership 與測試成熟。只有 runtime、scaling、GPU、故障隔離或 release cadence 明顯不同的單元，才優先拆成獨立部署。

## 4. 模組責任

### Backend

| 模組 | 責任 | 不應負責 |
| --- | --- | --- |
| `api` / `routes` | transport、auth、validation、response | 複雜業務規則、直接資料寫入 |
| `services` | use case、workflow、domain policy | FastAPI Request/Response、UI rendering |
| `repositories` | JSON/PostgreSQL/外部資料 adapter | 業務決策、HTTP mapping |
| `schemas` | DB schema、migration、typed contract | 執行 workflow |
| `realtime` | WebSocket 與事件傳遞 | 持久化業務真相 |
| `bootstrap` | 啟動、初始化、開發 server | 商業規則 |

### Frontend

| 模組 | 責任 |
| --- | --- |
| `frontend/kiosk` | 顧客點餐、會員、推薦、語音、付款與互動 |
| `frontend/admin` | 營運設定、會員、活動、RAG、成效與健康 |
| `frontend/shared` | 通用 API/realtime client、design token、UI primitive |

Kiosk 與 Admin 不共享 mutable business state、page state、DOM state 或 authentication state。

### AI 執行單元

- `Emotion-LLaMA` 與 `R1-Omni` 只提供模型能力，不直接寫入會員、訂單或營運資料。
- Core domain 依賴能力導向 Port，不依賴 provider 名稱或 SDK。
- Timeout、retry、circuit breaker、fallback 與 response normalization 應由 gateway/adapter 管理。

## 5. 資料與身分演進

目前 JSON 儲存保留為開發與相容路徑；商用資料以 PostgreSQL 為目標。

長期資料範圍：

```text
tenant
└── store
    └── device

user ─ role ─ permission ─ tenant/store scope

member(UUID)
├── encrypted PII
├── preferences
├── sessions
└── orders
```

原則：

- 新商業資料逐步加入 tenant/store/device scope。
- 手機號碼不作為長期公開 Domain ID；會員改用 UUID，PII 使用加密與 lookup hash。
- Schema 變更採 versioned migration。
- 破壞性變更使用 `expand → dual write/backfill → verify → switch read → contract`。

## 6. API 與相容性

- 現有 `/api/*`、`/kiosk`、`/admin` 與 WebSocket 在遷移期間保持相容。
- 新公開 API 優先使用 `/api/v1/*`。
- Request/Response 使用明確 Pydantic schema。
- 統一 error contract 應包含穩定 `code`、可讀 `message` 與 `request_id`。
- 前端 API 呼叫逐步集中至 typed/generated client。

## 7. 演進順序

1. 穩定文件、CI、typed contract 與 deployment baseline。
2. 建立 tenant/store/device、Admin identity/RBAC 與 migration framework。
3. 將前端大檔案拆成 feature modules，導入 Vite/TypeScript/Vitest/Playwright。
4. 導入 Redis、Worker、非同步 AI/RAG 工作與 provider gateway。
5. 補齊 OpenTelemetry、告警、SLO、備份還原演練與正式營運能力。

優先級與完成條件見 [FUTURE_MODULES.md](FUTURE_MODULES.md)。

## 8. 架構變更規則

需要 ADR：

- 改變 Modular Monolith / Microservices 策略。
- 改變資料 ownership、主要資料庫或一致性模型。
- 改變 Kiosk/Admin 部署邊界。
- 改變公開 API versioning、authentication 或多租戶隔離策略。
- 新增難以回復且跨模組的基礎設施依賴。

不需要 ADR：

- 模組內 refactor。
- 檔名、函式名或非公開 contract 調整。
- 小型效能修正、測試補強或 UI 細節。
