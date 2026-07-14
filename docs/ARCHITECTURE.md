# Project_2026 架構

- 文件版本：1.1
- 狀態：Active
- 最後更新：2026-07-14
- 架構策略：Modular Monolith First
- 執行模式：**方案 A — 單店本地端 Kiosk Pilot**（本機 / LAN 原生 process；禁止 Docker/K8s/微服務作為部署前提）

## 1. 系統目的

Project_2026 提供自助點餐、營運後台、會員個人化、推薦、語音互動、RAG 與情緒分析。架構目標是在不破壞現有 Kiosk/Admin 流程的前提下，逐步具備多門市、可測試、可部署、可觀測與可治理能力。

## 2. 目前架構

```text
Local Machine / LAN
├── PostgreSQL (commercial profiles)
├── Redis (optional)
├── API: python UI_API/main.py
├── Worker: python UI_API/backend/scripts/run_worker.py
├── Kiosk / Admin (served by API)
└── Optional: Ollama / Emotion-LLaMA / R1-Omni

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
- PostgreSQL migration 已具版本、checksum、status/validate、transaction advisory lock、idempotent apply 與 integration CI。
- AI provider 已可切換，適合逐步抽成 Port/Adapter。

目前限制：

- FastAPI 同時承擔 API、WebSocket、靜態前端與部分 background initialization。
- `config.py` 同時包含 infrastructure 與 runtime business settings。
- Admin 已建立 PostgreSQL identity、Argon2id password、revocable session 與 tenant/store scoped RBAC。Kiosk 已建立 per-device credential、short-lived session、rotation/revoke 與 typed principal；舊 Admin/Kiosk token 僅保留 feature-flagged compatibility window。
- Tenant → Store → Device 已完成 principal-derived scope enforcement；核心商業 scope 為 `NOT NULL`，availability、settings version、promotion、interaction/outcome 與 RAG ownership metadata 已有正式 PostgreSQL persistence。JSON 僅保留 Default Scope 開發／相容 adapter。
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

Redis 經 `CachePort`、`RateLimitPort`、`DistributedLockPort` adapter 提供跨 instance 短期狀態；key 綁 tenant/store 並雜湊 resource。Redis 不是商業資料 Source of Truth，failure policy 依 security/cache/correctness 分別 fail closed、degrade、caller-declared。

可靠背景工作由獨立 worker process 消費 PostgreSQL `background_jobs` 與 `order_outbox`：claim → `JobHandlerRegistry` 執行真正 handler（需有 `side_effect_id`）→ complete/retry/DLQ；outbox 經 `OutboxDeliveryRouter` 取得 sink ACK 後才可 `published_at`。支援 visibility timeout、retry/backoff、dead-letter、idempotent delivery 與 queue metrics。API process 只負責 enqueue/outbox write，不在 request path 執行長時間可重試工作。

Object storage（`services/object_storage_service.py`）以 Port/Adapter 管理 binary content：In-memory（test，`encryption=none-test`）、Local disk（development/pilot，atomic write、tenant namespace、path traversal 防護）、S3-compatible contract（缺 credential 時 EXTERNAL_BLOCKED）。Signed access 使用 HMAC-SHA256（object_id、tenant_id、expires、method）與外部注入 secret；Production 缺 secret 必須 fail fast。Metadata 可寫入 PostgreSQL `object_storage_metadata`（migration 0009）；binary 永不進 PostgreSQL。Encryption metadata 必須與真實 adapter 行為一致（`none-test` / `local-aes-gcm` / `provider-managed` / `kms-envelope`）。

Kiosk/Admin 目前由 Vite multi-entry build 分別驗證，production HTML/DOM 與 FastAPI `/static` serving 保持原路徑；Vitest 保護 shared transport，Playwright 保護本機 critical flows。完整契約見 [FRONTEND_TOOLCHAIN.md](FRONTEND_TOOLCHAIN.md)。

API v1 write surface（7A）提供 typed PATCH/PUT/POST for settings、availability、promotions、RAG lifecycle、fleet commands、order transition；legacy `/api/*` 保留相容。Frontend `shared/api/v1Client` 支援 get/post/put/patch；`frontend/legacy-api-allowlist.json` 凍結殘餘 `fetch('/api/...')` 並以 Vitest 阻止擴張。

Kiosk 與 Admin 不共享 mutable business state、page state、DOM state 或 authentication state。

### AI 執行單元

- `Emotion-LLaMA` 與 `R1-Omni` 只提供模型能力，不直接寫入會員、訂單或營運資料。
- Core domain 依賴能力導向 Port，不依賴 provider 名稱或 SDK。
- Timeout、retry、circuit breaker、fallback 與 response normalization 應由 gateway/adapter 管理。
- Text LLM 經 `services/llm_gateway_service.py`：`LLMRequest`/`LLMResponse`、model policy（local/cloud first/only）、safe retry、fallback、task schema validation、prompt version 與 long-lived executor timeout（不因 thread shutdown 失去 timeout 效果）。Production callers（AI Push、Voice、Payment Assist、Emotion Extract）只走 Gateway；僅 `OllamaAdapter`/`GeminiAdapter` 可 import `ai_services`。LLM 輸出不得直接成為交易決策。
- Multimodal evidence 經 `services/multimodal_evidence_gateway.py`：統一 Evidence contract（provider/version/confidence/signals/quality/latency/status）；Emotion-LLaMA / R1-Omni adapter 呼叫 `/predict`，null adapter 作 disabled/degraded。`emotion_service.analyze_event` 只走 Gateway；應用層不得直接 provider HTTP。Evidence 僅供 barrier/intervention 輸入，不得直接下單/付款；模型失敗回傳 no-evidence 且不阻塞 Checkout。
- RAG governance 經 `services/rag_governance_service.py` + `repositories/rag_governance_repository.py`：document version lifecycle（draft/review/published/retired）、rollback、published-only retrieval、retrieval trace 與 worker rebuild。Production metadata 使用 PostgreSQL migration 0010；content binary 經 object storage `content_ref`；JSON file 僅 development compatibility。
- Recommendation/Promotion governance 經 `services/recommendation_governance_service.py`：strategy version lifecycle、scope/window eligibility、deterministic **durable** experiment assignment、idempotent events 與 data-quality counters；PostgreSQL tables 於 migration 0011；因果推論僅限 experiment 設計。
- Fleet 經 `services/fleet_management_service.py`：allowlisted commands、config/rollout rings；PostgreSQL last-known state（0011）+ optional Redis presence TTL；JSON 相容。
- Analytics 經 `services/analytics_pipeline_service.py`：recursive PII payload reject、idempotent `PostgresAnalyticsSink`（`analytics_event_log`）、replay + checkpoint；JSON/InMemory 僅 test/dev。

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
- Scope 由 server configuration 或已驗證 identity 解析；未驗證的 `X-Tenant-ID`、`X-Store-ID`、`X-Device-ID` 不得改變資料範圍。
- Legacy single-store flow 使用 reserved Default Tenant / Default Store / Legacy Kiosk；新 repository query 使用明確 `CommercialScope`。
- 手機號碼不作為長期公開 Domain ID；Member 新路徑使用 UUID，tenant-scoped keyed lookup 與 authenticated encryption。Legacy phone column 僅作相容用途，讀取模式依 `legacy → dual → uuid_preferred → uuid_only` 漸進切換。
- Schema 變更採 versioned migration。
- Admin scope 由 database-backed `AdminPrincipal` 解析；permission、tenant 與 store 由集中式 server policy 驗證。正式 browser session 使用 HttpOnly cookie，database 只保存 token hash。
- Kiosk scope 由 database-backed `DevicePrincipal` 解析；credential 與 session 只保存 hash，rotation 具 overlap/cutover，revoke 只影響指定 device credential。
- Checkout 由 server-side pricing 建立 scoped Order aggregate；Order/items/promotion/outcome/outbox 使用單一 PostgreSQL transaction，client total 與任意狀態字串不是信任邊界。
- Process liveness 使用 `/live`；commercial readiness 使用 `/ready` 並驗證 PostgreSQL、clean migrations 與 configured scope。AI/RAG/Emotion degraded 不阻斷基本 checkout readiness。
- Structured logs 使用 request/trace 與 verified tenant/store/device correlation，先 redaction 再輸出；in-process metrics 定義穩定 commercial signal，外部 exporter 由 deployment adapter 接入。
- 破壞性變更使用 `expand → dual write/backfill → verify → switch read → contract`。

## 6. API 與相容性

- 現有 `/api/*`、`/kiosk`、`/admin` 與 WebSocket 在遷移期間保持相容。
- 新公開 API 使用 `/api/v1/*` typed DTO、統一 success/error envelope、唯一 operation ID 與 OpenAPI security metadata；詳細契約見 [API_V1.md](API_V1.md)。
- `/api/v1` 的 commercial scope 由已驗證 principal 在 server-side 解析，不接受未驗證 scope header 覆寫。
- Request/Response 使用明確 Pydantic schema。
- 統一 error contract 應包含穩定 `code`、可讀 `message` 與 `request_id`。
- 前端 API 呼叫逐步集中至 typed/generated client。

## 7. 演進順序

1. 穩定文件、CI、typed contract 與 deployment baseline。
2. 在既有 migration framework 上建立 tenant/store/device 與 Admin identity/RBAC。
3. 將前端大檔案拆成 feature modules，導入 Vite/TypeScript/Vitest/Playwright。
4. 導入 Redis、Worker、非同步 AI/RAG 工作與 provider gateway。
5. 補齊 OpenTelemetry、告警、SLO、備份還原演練與正式營運能力。

Deployment contract（API/Worker/PostgreSQL/Redis/AI gateway 邊界、staging-like compose、pre/post deploy 與 restore drill）見 [operations/DEPLOYMENT.md](operations/DEPLOYMENT.md)。

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
