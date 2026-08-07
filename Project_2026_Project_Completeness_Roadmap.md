# Project_2026 架構完整度與能力模組 Roadmap

> 更新日期：2026-08-06
> Baseline：`949479d`（repository hygiene 與 capability boundaries）
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
├── foundation/
│   ├── persistence/
│   ├── events/
│   ├── object_storage/
│   ├── observability/
│   └── security/
└── bootstrap/
```

`foundation/` 提供技術 primitives，不持有商品、訂單、會員、活動、RAG 或 AI 業務規則。Capability A 不得 import Capability B 的 `api.py`、`application.py`、`domain.py` 或 adapters；跨能力只允許 `interface.py`、`contracts.py` 或 `events.py`。

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

## 6A. 產品穩定化優先交付軌

本交付軌優先於 Phase 2 的大型模組搬移。目的不是暫停 capability architecture，而是先修復目前會阻斷點餐、語音與營運判讀的產品缺口，再把已穩定的行為收斂到能力模組。每一批必須通過自己的 Gate，後一批不得用未完成的前一批當作隱性前提。

### Batch P0 — Kiosk 關鍵路徑

狀態：**已完成**（PR #9，六條 Gate 各有失敗即紅的測試；CI 六項全綠）

- 推薦連續性：菜單可互動且有 eligible item 時必須持續顯示有效推薦；API 失敗改用最近有效結果或本機 fallback。
- 本機 fallback 只是佔位：它讓畫面不留白，但不得寫入商業曝光或點擊。商業觸點必須帶 server 的 decision 或 campaign，否則一律不送（ADR-0020）。
- Voice Turn：麥克風、STT、LLM 與成功輸出可播放的 TTS 音檔都是成功條件；攝影機與情緒分析只能 advisory，不得阻斷 Voice。
- TTS 經有限次 retry 後仍無法輸出音檔（含回傳空音訊），終局為 `Voice Playback Failure`；保留文字作為錯誤證據，但不得標記 Voice Turn 成功。
- 音檔已輸出後的播放結果不做逐回合回報：瀏覽器播不出來時顧客看到明確失敗與保留文字，但不改寫 server 紀錄；TTS 是否真的送達顧客耳朵，由 P1 維運健康的服務綠燈與現場人工驗證負責。
- 「直接點餐」與兩個「略過，直接點餐」共三個入口，使用同一個 Guest Ordering Choice 與同一條 server-authoritative entry path；未接上 entry hook 必須可見失敗，不得靜默進入菜單。
- 會員限定優惠在點餐途中叫出的會員選擇，不是入口決策；它不得發出 entry flow 指令，也不得覆寫啟動時注入的 entry hooks。

Gate：推薦不出現空白／暫停狀態、佔位推薦不產生商業觸點、Voice 成功必須有 TTS 音檔輸出證據、缺少攝影機仍可完成 Voice、三個訪客按鈕 contract 一致且各自有穿過真實接線的測試、API 失敗可見且可 retry。

Gate evidence（PR #9）：

| Gate 條目 | 證據 |
| --- | --- |
| 推薦不出現空白／暫停狀態 | `tests/e2e/recommendation-continuity.spec.ts`（`/api/ai_push` 強制 500） |
| 佔位推薦不產生商業觸點 | 同上，含「真實推薦仍照常回報」的反向驗證 |
| Voice 成功必須有 TTS 音檔輸出證據 | `tests/test_voice_turn_playback_contract.py` |
| 缺少攝影機仍可完成 Voice | `tests/test_voice_turn_media_degradation.py` |
| 三個訪客按鈕 contract 一致 | `tests/unit/guest-ordering-wiring.test.ts`（載入真實 `member.js` 綁定） |
| API 失敗可見且可 retry | 上述訪客與推薦兩組測試 |

### Batch P1 — Admin 核心營運與精簡 RAG

狀態：**進行中**

- 營運總覽只顯示 server accepted 的 Voice、推薦、活動 CTA 次數，以及明確標示的「已確認訂單金額」。
- Voice 成功數的口徑必須在畫面上寫明：它是「語音已產生並送出」的次數，不是顧客實際聽到的次數；顧客端播放失敗不進入這個數字，由維運健康的 TTS 綠燈與現場驗證涵蓋。
- 推薦次數必須排除 source 為 `local_default`、`local_fallback` 或空白的事件——那些是 kiosk 在 API 失敗時自己挑的佔位品項，事件保留是為了讓後續轉換有來源可對應，不是推薦成效（ADR-0054）。
- 維運健康只顯示 UI API、Ollama、R1 與 RAG retrieval API 的連線狀態、latency、觀測時間與安全錯誤。
- RAG 只保留 Knowledge Item CRUD、單一已發布 Retrieval Method 與 ad hoc retrieval test。
- 新資料結構、migration 與核心 RAG tests 全部通過後，永久刪除 pre-pilot evaluation、readiness、版本歷史、import history、舊 alerts/audit/history；本次已明確授權不備份且不可復原。

Gate：Admin 沒有舊 KPI／內部 DB 與 log 面板；RAG 三條主流程可獨立運作；刪除清單有 migration evidence；保留 Knowledge Items、published index、active retrieval config 與 pending publish work。

### Batch P2 — Emotion Diagnostics

狀態：**等待 P1 Gate**

- 三個互斥模式：Off、Periodic Ordering、Voice Only。
- Periodic Ordering 依序執行 capture → inference → record；片段 2–30 秒、預設 5 秒，不允許並行 backlog。
- Voice Only 使用 Voice Turn 對齊的 audiovisual evidence；未通過 audio-only acceptance 時，只有麥克風就明確 skip emotion，不阻斷 Voice。
- Admin 即時測試支援一次性影音錄製、2–30 秒、自訂 prompt／還原 server default，raw media 在 inference 後刪除。
- 紀錄只保留時間、事件、模型、強度、表情、聲音、描述；固定 emotion/intensity enum，store-scoped 保存 30 天。
- Emotion 永遠只作客服參考，不得自動改變回答、推薦、價格或訂單。

Gate：三模式互斥、ordering boundary 正確、submitted failure 可安全記錄、raw media/transcript 不落地、30 天清除可驗證。

### Batch P3 — Project Core Brain

狀態：**等待 P2 Gate**

- 建立獨立 `project-analyst` sidecar，只接受手動 analyze/reanalyze。
- 只讀取 allowlist 內的 tracked source/tests/docs/non-secret config、CodeGraph facts、Git status/diff、Docker/API readiness 與明確執行的 tests。
- 禁止讀取 `.env`、secrets、客戶資料、raw media、home/external paths、Docker socket 與任意 shell。
- Codex、Claude、Grok 只有通過版本、認證、headless、read-only restriction 與 JSON schema probe 才成為 Ready Profile；每次明確選一個，不自動 fallback。
- 僅保留最新成功報告；失敗重掃保留舊報告並標示 stale。非核心提案未來只能輸出隔離 patch proposal，不 apply/commit/push。

Gate：sidecar non-root/read-only/cap-drop/resource bounds、provider readiness contract、證據 allowlist、latest-report atomic replace、失敗不破壞舊報告。

### Batch P4 — Optimization Lab（reference-only）

狀態：**等待 P3 Gate**

- 與 Project Analyst 分離為獨立 module/container，只做手動單店單日分析，不修改 LLM、Prompt、RAG、檔案，也不 push。
- 保存去識別化 Voice Interaction Evidence 30 天：遮罩後 STT、完整 LLM answer、RAG hit、voice outcome、安全失敗、retry/correction；不保存 raw audio、會員／裝置／session／訂單／付款識別與個人 emotion。
- 每次 run 在開始時凍結 Asia/Taipei 的單日 evidence IDs；今日可產出 partial report 並記錄 cutoff。
- Codex／Claude／Grok 各自顯示 provider-native model 與 effort；一次只選一個 analyzer，無 fallback。
- Finding 只能分類為 RAG Knowledge Gap、Prompt Behavior、Model Capability、Product Pipeline 或 Insufficient Evidence；1–2 筆只可列 Observation Signal，至少 3 筆相似或 synthetic reproducibility 才能給 Reference Guidance。
- 具體 guidance 必須先通過 Voice/RAG offline acceptance；否則只能輸出 Unverified direction。
- customer evidence scope 需要 provider-specific authorization、automation credential、outbound disclosure、retention acceptance 與 per-run egress audit。

Gate：reference-only policy 由 API 強制、敏感證據需 `optimization.evidence.read` 加 15 分鐘 manager step-up、報告不複製 transcript、evidence expiry 可驗證、六段報告 contract 固定。

### 共通完成定義

每一批都必須具備 domain/unit、HTTP contract、failure、retention/security 與 frontend consumer tests；Docker Compose 是唯一支援 runtime，host Conda 不屬於完成證據。Roadmap 狀態只能由同一 commit 的 test、migration、OpenAPI 與 smoke evidence 更新，不能以畫面存在或 endpoint 可回 200 當作完成。

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

目前只執行 Batch P0，通過後才開啟 Batch P1：

1. 建立推薦連續性、Voice/TTS 終局與 Guest Ordering Choice 的 failure-first tests。
2. 修復 Kiosk 行為並執行 frontend unit、typecheck、build 與 API contract tests。
3. 在 Docker Compose 執行 Kiosk smoke，保存同一 commit 的 Gate evidence。
4. P0 Gate 通過後，先建立精簡 RAG replacement migration 與 preservation tests。
5. 只有 replacement migration 在乾淨 DB 與現有 schema upgrade 都通過，才執行已授權的永久 legacy RAG purge。
6. 依序開啟 Emotion、Project Analyst 與 Optimization Lab，不平行引入跨批次資料 authority。

相關決策：

- [ADR-0021](docs/adr/0021-adopt-docker-first-immutable-pilot-delivery.md)
- [ADR-0022](docs/adr/0022-preserve-ordering-during-shared-infrastructure-degradation.md)
- [ADR-0023](docs/adr/0023-organize-the-application-by-business-capability-contracts.md)
- [ADR-0024](docs/adr/0024-separate-admin-and-kiosk-product-frontends.md)
