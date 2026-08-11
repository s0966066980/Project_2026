# UI_API 核心應用

`UI_API/` 是 Project_2026 的 production application source。FastAPI 提供能力 API，Admin 與 Kiosk 是兩個獨立 browser applications，worker 處理 durable jobs 與 outbox。唯一支援的執行與驗證環境是 Docker Compose。

## 架構方向

後端維持 modular monolith，不按 Admin/Kiosk 複製商業規則，而按十個 Business Capability Modules 垂直整理：

1. Identity & Device Access
2. Catalog & Availability
3. Ordering & Checkout
4. Member
5. Campaign & Promotion
6. Recommendation & Interaction Analytics
7. Knowledge/RAG
8. Voice Assistance
9. Emotion Diagnostics
10. Operations & Configuration

每個 capability 最終集中 HTTP transport、application workflow、domain rules、ports、adapters 與 tests。每張 business table 只有一個 capability 可寫；跨模組同步協作只透過 Capability Interface，durable consequences 使用 event/outbox。

```text
backend/
├── capabilities/            # 逐模組遷移的垂直業務能力
│   └── <capability>/
│       ├── api.py
│       ├── application.py
│       ├── domain.py
│       ├── interface.py
│       ├── ports.py
│       └── adapters/
├── foundation/              # persistence、events、objects、observability primitives
├── bootstrap/               # composition root 與 process startup
├── routes/                  # 遷移中的 legacy transports
├── services/                # 遷移中的 workflows／compatibility shims
├── repositories/            # 遷移中的 persistence adapters
├── schemas/migrations/      # PostgreSQL forward migrations source of truth
└── scripts/                 # production-adjacent maintenance／worker CLIs
```

目前仍處於 Transitional Modular Monolith：Identity 已有 module 雛形，但 `routes/v1_routes.py` 仍跨多個 domain，`routes/services/repositories` 也尚未完成垂直搬遷。新增功能不得擴大這些 legacy ownership。

## Admin 與 Kiosk

Admin 和 Kiosk 必須各自擁有 UI/UX、bootstrap、state、features、styles、assets 與 tests，不能互相 import 或以 runtime mode 切換產品身分。

```text
frontend/
├── admin/                   # Admin application
├── kiosk/                   # Kiosk application
├── shared/                  # 僅 generated clients、tokens、stateless primitives/transport
├── tests/                   # product boundary、unit 與 E2E tests
├── vite.config.ts
├── vitest.config.ts
└── playwright.config.ts
```

`shared/` 不得持有 product feature、auth、page、state 或全域 product CSS。FastAPI/Pydantic 產生 OpenAPI 與 TypeScript client；feature code 最終不得直接呼叫 legacy `/api/*` 或自行維護 transport DTO。

現況債務：Kiosk `app.js` 與 Admin `admin.js` 仍偏大；Kiosk 尚有 Admin runtime mode 判斷；`shared/styles.css` 混合兩端 selector；raw `fetch` 與 legacy client 仍在遷移中。

## 資料與執行邊界

- PostgreSQL 是 tenant、store、device、identity、catalog、member、ordering、campaign、Knowledge publication、Retrieval configuration/checks 與 settings 的 authoritative store。
- `backend/schemas/migrations/` 是 schema source of truth；目前 migration head 為 `0027_remove_pre_pilot_rag_history`。
- Redis 只提供 shared cache、rate limiting 與 distributed lock，不持有 authoritative business data。
- Object bytes 使用 local/S3 adapter；PostgreSQL 保存 metadata。
- `backend/capabilities/catalog/seed/menu.json` 是 Catalog 的 seed，只在門市尚無品項時匯入一次，不是 runtime source of truth。
- `learning_data/settings.json` 是待移除的 compatibility/test data，不得成為 Pilot settings authority。
- AI、RAG、STT/TTS、Emotion provider 可以 degraded，但不得改寫 checkout transaction authority。

## 啟動與狀態

從 repository 根目錄啟動預設 NVIDIA GPU stack：

```bash
bash docker/scripts/setup.sh
```

CPU 模式：

```bash
bash docker/scripts/setup.sh --cpu
```

查看 app、worker 與 migration log：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  -f docker/compose.ai-gpu.yaml \
  logs -f app worker migrate
```

`/live` 只表示 process 存活；`/ready` 檢查必要依賴並列出 optional degradation。Payment/POS 目前只有 manual adapters，Order Confirmation 只建立 `Payment Pending` 訂單。

## Maintenance CLI

`backend/scripts/` 是必要的 production-adjacent entry points，不是可刪除的 root helper scripts：

| Script | Responsibility |
| --- | --- |
| `manage_runtime_persistence.py` | migration/status/write probe；Compose `migrate` 入口 |
| `run_worker.py` | durable job/outbox worker；Compose `worker` 入口 |
| `manage_admin_identity.py` | trusted Admin/RBAC provisioning |
| `verify_member_identity_migration.py` | Member UUID/PII integrity |
| `validate_commercial_scope.py` | tenant/store/device scope integrity |
| `validate_local_environment.py` | environment profile checks |
| `validate_local_pilot_data_paths.py` | 防止 Pilot 商業資料落回 JSON |
| `validate_voice_turn_performance.py` | Voice Turn performance evidence |

透過 app image 查看命令，不需要 host Python/Conda：

```bash
docker compose --env-file .env \
  -f docker/compose.yaml \
  -f docker/compose.ai.yaml \
  run --rm --no-deps app \
  python backend/scripts/manage_runtime_persistence.py --help
```

寫入型 maintenance command 必須 dry-run、明確 flag 或具備可觀測的冪等語意，且不得輸出 secrets、完整 PII 或 document content。

## 驗證

核心 container tests 與 health smoke：

```bash
docker/scripts/test.sh
```

AI image dependency smoke：

```bash
docker/scripts/test-ai.sh
```

Frontend contract/type tests：

```bash
cd UI_API/frontend
npm ci
npm run typecheck
npm test
```

Backend tests 的正式 surface 是 capability interface、HTTP contract 與 adapters。PostgreSQL、Redis、object storage integration tests 必須使用實際 provisioned dependency，不得用 in-memory fake 冒充 integration evidence。

完整 Docker 操作、R1 權重與限制見 [Repository README](../README.md) 和 [Docker README](../docker/README.md)。架構詞彙與決策見 [CONTEXT.md](../CONTEXT.md) 與 [ADRs](../docs/adr/)。
