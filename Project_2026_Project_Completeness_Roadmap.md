# Project_2026 架構完整度與能力模組 Roadmap

> 更新日期：2026-08-05
> Baseline：`725c5a3`（Docker-first runtime 與 capability architecture）
> 目標：單店 Admin＋Kiosk 點餐系統，維持 modular monolith，逐能力建立可驗證的獨立契約
> Runtime：Docker Compose；host Python/Conda 不屬於支援路徑

## 1. 本輪結論

「全部功能 API 化」不代表每個按鈕建立一個 endpoint，也不代表立即拆成微服務。Project_2026 採十個垂直 Business Capability Modules：

- Kiosk、Admin 與 out-of-process caller 使用 versioned Capability HTTP API。
- 同一 app process 的模組使用 typed Capability Interface；durable consequences 使用 event/outbox。
- PostgreSQL instance 共用，但每筆 authoritative business data 只有一個 module 可寫。
- 每個 operation 明示 principal 與 permission，不使用一個全域角色規則涵蓋所有能力。
- Admin/Kiosk 是兩個獨立 frontend applications，不共享 feature、state、auth、layout 或 product CSS。
- FastAPI/Pydantic 產生 OpenAPI 與唯一 TypeScript client，feature code 不手寫 transport contract。

這個目標是「模組契約與故障隔離」，不是 process crash isolation。R1、Ollama、PostgreSQL 與 worker 繼續使用既有 Docker process boundary；只有觀測證據顯示 modular monolith 無法滿足故障需求時，才評估抽出新服務。

## 2. 現況證據

### 2.1 已具備

- Docker Compose 已包含 app、worker、PostgreSQL、migration、Ollama、R1-Omni 與 health checks。
- FastAPI 已有 route registry、typed `/api/v1` envelope、RBAC、commercial scope 與 OpenAPI。
- Backend 已有 21 個 `create_router()` factories（包含商業與受 flag 控制的 routes），以及 cart、checkout、ordering entry、knowledge publication、retrieval check、voice turn 等 module 雛形。
- PostgreSQL 目前有 80 張 public tables；migration head 是 `0025_store_menu_items`。
- Transactional outbox、durable jobs、dead letter、checkout idempotency 與 outcome recovery 已存在。
- Frontend 已有 Admin/Kiosk Vite entries、部分 typed client 與少量 unit/E2E tests。

### 2.2 主要耦合

- `backend/routes/v1_routes.py:create_router()` 仍有 1,128 行，跨至少 48 個 route/application dependencies。
- Backend 同時存在 `modules/`、`routes/`、`services/`、`repositories/`，單一功能規則散在多個水平資料夾。
- `AppContainer` 尚未成為十個能力的一致 composition root；多數 route 直接使用 global service/repository。
- Frontend 至少 10 個檔案存在 raw `fetch`，掃描到 46 個呼叫點，並混用 `/api/*`、`/api/settings/*`、`/api/rag/*` 與 `/api/v1/*`。
- Kiosk `app.js` 約 2,627 行，仍包含 Admin runtime mode；`shared/styles.css` 仍混有兩個產品 selector。
- `UI_API/deploy/postgres`、`config/profiles/local-pilot.env.example`、`learning_data/settings.json` 與 repository runtime paths 存在不同年代的執行假設。

### 2.3 嚴格完成狀態

```text
Business Capability Modules passed: 0 / 10
Independent Product Frontends passed: 0 / 2
Current vertical slice: Catalog & Availability
```

已有 endpoint 或搬入新目錄不算完成。只有通過 Module Independence Gate 才能增加上述數字。

## 3. 目標結構

### 3.1 Backend

```text
UI_API/backend/
├── capabilities/
│   ├── identity_access/
│   ├── catalog/
│   ├── ordering/
│   ├── member/
│   ├── campaign_promotion/
│   ├── recommendation_analytics/
│   ├── knowledge_rag/
│   ├── voice/
│   ├── emotion/
│   └── operations_configuration/
│       ├── api.py
│       ├── application.py
│       ├── domain.py
│       ├── interface.py
│       ├── ports.py
│       └── adapters/
├── platform/
│   ├── persistence/
│   ├── events/
│   ├── object_storage/
│   ├── observability/
│   └── security/
└── bootstrap/
```

`platform/` 提供技術 primitives，不持有商品、訂單、會員、活動、RAG 或 AI 業務規則。Capability A 不得 import Capability B 的 `api.py`、`application.py`、`domain.py` 或 adapters；跨能力只允許 `interface.py`、`contracts.py` 或 `events.py`。

### 3.2 Frontend

```text
UI_API/frontend/
├── admin/
│   ├── app/
│   ├── features/
│   ├── styles/
│   ├── assets/
│   └── tests/
├── kiosk/
│   ├── app/
│   ├── features/
│   ├── styles/
│   ├── assets/
│   └── tests/
└── shared/
    ├── api/generated/
    ├── tokens/
    ├── primitives/
    └── transport/
```

Admin/Kiosk 各自 build、typecheck、unit test 與 E2E。`shared/` 不得 import 任一 product，也不得保存 product state、auth、feature controller、page layout 或 global product selector。

## 4. 十個能力與遷移波次

| Wave | Capability | Criticality | 主要責任 | Provisional data authority |
| ---: | --- | --- | --- | --- |
| 1 | Catalog & Availability | Core | 商品、分類 label、圖片 reference、供應狀態、Kiosk catalog view | `store_menu_items`, `store_availability`, catalog object metadata |
| 1 | Identity & Device Access | Core | Admin/Device principal、session、RBAC、credential、fleet access | `admin_*`, `device_*`, `devices`, `fleet_*` |
| 1 | Operations & Configuration | Core | commercial settings、capability status、health、audit、operator actions | `commercial_settings_versions`, `admin_audit_logs` |
| 2 | Member | Operational | 會員、偏好、consent、member session/history | `members`, `member_*` |
| 2 | Campaign & Promotion | Operational | campaign lifecycle、promotion rules、published push copy | `campaign_*`, `promotion_*`, `menu_item_push_copy`, `push_copy_batches` |
| 2 | Recommendation & Interaction Analytics | Optional | recommendation decisions/events、touch attribution、interaction analytics | `recommendation_*`, `commercial_touch_events`, `interaction_events`, `analytics_*` |
| 3 | Ordering & Checkout | Core | entry flow、session、cart、quote、confirmation、order、manual payment handoff | `ordering_*`, `checkout_*`, `confirmed_orders`, `orders`, `order_*` |
| 4 | Knowledge/RAG | Optional | knowledge lifecycle、publication、retrieval checks/evaluation | `knowledge_*`, `publication_*`, `rag_*`, `published_knowledge_pointers` |
| 4 | Voice Assistance | Optional | voice turn journal、STT/LLM/TTS orchestration、cart command proposal | `voice_turns`, `voice_turn_events` |
| 4 | Emotion Diagnostics | Optional | R1 evidence、diagnostic records、assistance outcome | emotion/intervention records assigned during detailed inventory |

`Provisional data authority` 必須在每個 slice 開始前以 migrations、repository SQL 與 runtime trace 校正。表名相近不等於 ownership 已證明。

## 5. Module Independence Gate

每個 capability 必須同時滿足：

1. **Interface**：只有一個對其他模組公開的 typed Capability Interface。
2. **HTTP contract**：只有一組 capability-centered `/api/v1/{capability}` routes、DTO、error codes 與 operation IDs。
3. **Data authority**：table owner 清楚；沒有跨能力 repository import、SQL 或 write。
4. **Authorization**：每個 operation 宣告 principal 與最小 permission。
5. **Failure behavior**：Core fail closed；Operational fallback 被測試；Optional 可獨立 degraded/disabled。
6. **Tests**：domain/unit、interface、PostgreSQL adapter、HTTP contract、consumer 與 failure tests 通過。
7. **Frontend callers**：Admin/Kiosk 使用 generated client，沒有 raw legacy fetch。
8. **Migration**：legacy route 只轉接到權威 interface，usage telemetry 歸零後刪除。
9. **Observability**：capability status、latency、error、degradation 與 operator action 可定位。
10. **Evidence**：CI、OpenAPI diff、migration、smoke 與 Roadmap evidence 都指向同一 commit/artifact。

## 6. 執行階段

### Phase 0 — Baseline checkpoint

狀態：**完成**

- Docker CPU/GPU Compose config、shell syntax、TypeScript typecheck 通過。
- Docker-first 與 capability architecture 已提交為 `725c5a3`。
- ADR-0021～0024 與 glossary 已建立。

### Phase 1 — Repository hygiene and guardrails

狀態：**已完成**

- 合併重複 README，建立最小權威文件集。
- 刪除 generated design-system、repository runtime placeholders 與可重建 cache/log/build artifacts。
- 建立十能力 manifest、backend import rules 與 frontend product import rules。
- 重建本 Roadmap。
- 不搬移 business behavior、不變更 endpoint contract。

### Phase 2 — Catalog & Availability vertical slice

狀態：**未開始**

1. 校正 `store_menu_items`、`store_availability`、圖片 metadata 的唯一 owner。
2. 建立 Catalog domain/application/interface/ports/adapters。
3. 建立 `/api/v1/catalog/items`、item image 與 availability commands。
4. 由 FastAPI OpenAPI 產生 TypeScript client。
5. Admin 與 Kiosk 各自建立 Catalog feature；移除 Kiosk/Admin mode 共享。
6. Legacy `/menu*`、`/availability*` 只轉接新 interface，記錄 usage。
7. Contract、PostgreSQL、permission、failure、Admin/Kiosk consumer tests 通過後刪 legacy routes。
8. 將 `menu_data/menu.json` 移至 Catalog seed/fixture；將 menu/category images 移至 Kiosk assets。

### Phase 3 — Wave 1 remaining capabilities

- Identity & Device Access。
- Operations & Configuration。
- 以 Docker Pilot external config 取代 stale `config/profiles/local-pilot.env.example`。
- 將 `UI_API/deploy/postgres` 的 runtime-role/init 能力搬入 canonical `docker/` 後刪除舊 Compose。
- 將 `learning_data/settings.json` 正式設定移入 Operations data authority，測試值移入 fixtures。

### Phase 4 — Wave 2 commercial capabilities

- Member。
- Campaign & Promotion。
- Recommendation & Interaction Analytics。

先穩定會員、活動與推薦的 read contracts，再允許 Ordering 只依賴其 published interfaces/snapshots。

### Phase 5 — Wave 3 ordering transaction

- Ordering Entry、Session、Cart、Quote、Checkout Confirmation、Order 與 Payment Pending handoff 收斂為一個深模組。
- 保留 server-authored pricing、idempotency、outcome unknown recovery 與 transactional outbox。
- 禁止 AI、browser total 或跨能力直接 SQL 成為 transaction authority。

### Phase 6 — Wave 4 intelligent capabilities

- Knowledge/RAG。
- Voice Assistance。
- Emotion Diagnostics。

三個能力有獨立 status、timeout、permission、data retention 與 failure tests；Ollama、NIM、STT/TTS、R1 是 adapters，不是 capability ownership。

### Phase 7 — Legacy closure

- raw frontend fetch 歸零。
- `/api/*` compatibility telemetry 歸零。
- 刪除 giant `v1_routes.py`、已空的 horizontal folders 與 legacy allowlists。
- `Business Capability Modules passed = 10/10`、`Independent Product Frontends passed = 2/2`。

## 7. Repository 清理政策

### 已清理

- root Conda scripts。
- generated `design-system/`。
- repository `runtime/` placeholders 與 ignored runtime logs。
- `.mypy_cache`、`.ruff_cache`、`__pycache__`、frontend `node_modules/dist/coverage/test-results`。
- 重複的 backend/frontend 子層 README；必要內容收斂至 `UI_API/README.md`。

### 先替代再刪除

| 目前位置 | 替代條件 |
| --- | --- |
| `config/profiles/local-pilot.env.example` | Docker Pilot external config 與 fail-fast validation 完成 |
| `UI_API/deploy/postgres/` | runtime role、secret 與 WAL/backup requirements 搬入 canonical Docker path |
| `UI_API/learning_data/settings.json` | Operations settings authority 與 test fixtures 完成 |
| `UI_API/menu_data/menu.json` | Catalog seed/fixture 完成 |
| frontend root images/categories | Kiosk assets 搬移且 build/E2E 通過 |
| horizontal `routes/services/repositories/modules` | 對應 capability 通過 Independence Gate |

永遠不得以清理名義刪除 `.env`、R1 weights、PostgreSQL business data、Docker volumes、backups 或 secrets。

## 8. 文件權威

保留的主要文件只有：

- `README.md`：安裝、啟動、服務入口。
- `UI_API/README.md`：application 架構與操作。
- `docker/README.md`：Docker runtime。
- `R1-Omni/README.md`：R1 runtime/weights。
- `CONTEXT.md`：專案詞彙。
- 本 Roadmap：完成度、wave、gate 與下一步。
- `docs/adr/`：難逆轉的決策歷史。
- `docs/agents/` 與 `AGENTS.md`：agent workflow。
- `tools/README.md`：非 production tools。

不要為每個資料夾建立 README。模組責任由 interface、manifest、tests 與本 Roadmap 表達；只有真正的 operator runbook 才新增獨立文件。

## 9. 工作流程

```text
Roadmap capability/wave
        ↓
GitHub Issue / acceptance criteria
        ↓
short-lived branch
        ↓
implementation + contract/failure tests
        ↓
PR required checks
        ↓
merge main + auto-delete branch
        ↓
更新 Independence Gate evidence
```

單一 PR 不跨兩個 capabilities 的 data ownership；純 mechanical move 與 behavior change 分開提交。任何 legacy deletion 都必須有 replacement、consumer migration、usage evidence 與 rollback path。

## 10. 下一個可執行工作

Phase 1 完成並提交後，只建立 Catalog & Availability slice：

1. 產生 table/route/frontend caller inventory。
2. 寫 Catalog Interface 與 contract tests。
3. 建立 capability-centered v1 API 與 generated client pipeline。
4. 分開 Admin/Kiosk Catalog features/styles/assets。
5. 以 telemetry 驗證 legacy caller 歸零。
6. 通過第一個 Module Independence Gate，再開始下一個 capability。

相關決策：

- [ADR-0021](docs/adr/0021-adopt-docker-first-immutable-pilot-delivery.md)
- [ADR-0022](docs/adr/0022-preserve-ordering-during-shared-infrastructure-degradation.md)
- [ADR-0023](docs/adr/0023-organize-the-application-by-business-capability-contracts.md)
- [ADR-0024](docs/adr/0024-separate-admin-and-kiosk-product-frontends.md)
