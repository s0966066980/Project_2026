# Project_2026 徹底升級與逐項驗證執行計畫

> 文件定位：本文件不是「最低限度修改清單」，而是將 Project_2026 從目前的
> **Transitional Modular Monolith / Local Pilot
> NOT_READY**，逐步收斂為可版本化、可測試、可部署、可復原、可維運、可在實體
> Kiosk 長時間運作的 **Commercial V1 單店 Local-First Kiosk Product**。
>
> 核心執行規則：**一次只處理一個可驗證項目；修改完成立即測試；測試失敗立即停止，不得帶病進入下一項；修復並重新執行該
> Gate，直到全綠後才進入下一項。**
>
> 基準日期：2026-08-12\
> 基準分支：`main`\
> 主要產品：`UI_API/`\
> 目標：單店、單機或可信任 LAN、Local-First AI、PostgreSQL authoritative
> persistence、AI 可降級但核心點餐不可中斷。
>
> ---
>
> **收錄附註（2026-08-12，非原文）**：本文件收錄為 repository 的路線權威，原文未改。
> 兩點與現況不符，處置記錄在 [`README.md`](README.md)：
>
> 1. **0.1 的升級分支**不採用，工作維持在單一 `main`（專案擁有者指示）。
> 2. **數個項目在本文件寫成當日稍早已完成**（02、04、13 的 HTTP 半、14、16、19、24、36 等）。
>    起點以 `README.md` 的逐項對照為準，不從第一項重做。
>
> 「現在通過了什麼」一律以
> [`Project_2026_Execution_Plan.md`](../../Project_2026_Execution_Plan.md) 為準。

------------------------------------------------------------------------

## 0. 最終目標

完成本計畫後，Project_2026 應從：

``` text
Git Repository
   ↓
Developer manually builds/runs
   ↓
Docker Compose
   ↓
Kiosk / Admin / AI
```

升級為：

``` text
GitHub
  │
  ├── Pull Request Quality Gates
  ├── Security Gates
  ├── Contract Gates
  ├── Integration Gates
  └── Release Gates
          │
          ▼
   Versioned Release
          │
          ├── immutable application image
          ├── migration image/process
          ├── worker image/process
          ├── SBOM / checksums
          ├── release manifest
          └── rollback metadata
                  │
                  ▼
             Kiosk Appliance
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
   FastAPI     Worker    PostgreSQL
       │
       ├── Kiosk
       ├── Admin
       └── Adapters
             │
     ┌───────┼─────────┐
     ▼       ▼         ▼
   Ollama   Voice    R1-Omni
     │
     └── AI degraded ≠ checkout failure

Appliance:
Linux → Docker → health/readiness → Chromium kiosk mode
      → watchdog → backup → restore → update → rollback
```

最終產品必須具備以下特性：

1.  **核心交易權威明確**：價格、promotion
    eligibility、cart/order、payment state、member scope、RBAC 均由
    server/domain 決定。
2.  **AI 完全可降級**：Ollama、R1-Omni、STT、TTS、RAG
    任一故障不得阻止基本點餐與結帳。
3.  **真正 Modular Monolith**：domain 不再透過 legacy service/repository
    互相穿透。
4.  **Kiosk 與 Admin 真正分離**：不共用產品狀態、不互相 import、不存在
    runtime mode spaghetti。
5.  **PostgreSQL 是商業環境唯一 authoritative database**。
6.  **非同步任務可靠**：transactional
    outbox、retry、idempotency、dead-letter/recovery 有測試證據。
7.  **可重建部署**：新機器可以從 release + config + model manifest +
    backup 重建。
8.  **可升級、可回滾**：失敗 release 不會把現場設備鎖死。
9.  **可觀測**：logs、metrics、health、readiness、worker backlog、AI
    provider 狀態可診斷。
10. **可復原**：PostgreSQL、objects、RAG metadata/config 有實際 restore
    drill。
11. **安全預設**：production/pilot fail closed。
12. **實機驗證**：不是「Docker 能啟動」就宣告完成，而是通過
    burn-in、斷網、重啟、AI crash、DB recovery 等測試。
13. **Payment/POS 使用 Port/Adapter**，核心 ordering 不綁任何特定廠商。
14. **Release 有證據鏈**：commit → CI → image digest → migration →
    deployment → smoke test。

------------------------------------------------------------------------

# 1. 不可違反的執行原則

## 1.1 Sequential Gate 原則

每個項目固定使用：

``` text
PRECHECK
   ↓
CHANGE
   ↓
STATIC TEST
   ↓
UNIT TEST
   ↓
INTEGRATION TEST
   ↓
REGRESSION TEST
   ↓
DOCKER/SMOKE TEST（適用時）
   ↓
EVIDENCE
   ↓
COMMIT
   ↓
NEXT ITEM
```

任何一層失敗：

``` text
FAIL
 ↓
STOP
 ↓
分析 root cause
 ↓
修正
 ↓
從該項目的完整 Gate 重新測試
 ↓
PASS
```

禁止：

``` text
A 有錯
↓
「之後再修」
↓
先做 B/C/D
```

## 1.2 一項一提交

建議每個原子工作：

``` text
refactor(ordering): introduce ordering application port
test(ordering): cover checkout idempotency
refactor(frontend): extract kiosk cart feature
ops(backup): add postgres restore verification
```

不要一次 commit：

``` text
refactor everything
```

## 1.3 每個 Phase 都必須有 Baseline Regression

每完成一個 Phase：

``` bash
backend full test
frontend full test
migration test
security test
docker core test
```

適用時再加：

``` bash
docker AI test
E2E
hardware smoke
```

## 1.4 不做 Big Bang Rewrite

「徹底升級」不等於把現有程式全部刪掉重寫。

正確方式：

``` text
建立新 boundary
→ 加 characterization tests
→ 一條 use case 搬遷
→ 新舊行為比對
→ 切換 caller
→ 測試
→ 刪 legacy
→ 再測試
```

## 1.5 Definition of Done

一個項目只有同時符合以下條件才算完成：

-   [ ] 程式碼已修改
-   [ ] 新增或更新測試
-   [ ] targeted tests PASS
-   [ ] regression tests PASS
-   [ ] architecture/security rules PASS
-   [ ] 文件同步
-   [ ] 無新的 TODO 取代真正實作
-   [ ] 無 silent fallback
-   [ ] 無 disabled test 逃避失敗
-   [ ] 留下 evidence
-   [ ] commit 可獨立回退

------------------------------------------------------------------------

# 2. Phase 0 --- 建立不可移動的 Baseline

目的：在大規模重構前，先證明「目前版本到底會什麼」，否則之後無法知道是升級還是破壞。

## 0.1 建立升級分支

建議：

``` bash
git checkout main
git pull --ff-only
git checkout -b upgrade/commercial-v1
git status
git rev-parse HEAD
```

記錄：

``` text
BASELINE_COMMIT=<sha>
UPGRADE_BRANCH=upgrade/commercial-v1
DATE=<date>
```

### Gate 0.1

-   [ ] working tree clean
-   [ ] baseline SHA 已記錄
-   [ ] 不直接在 main 做大規模重構

------------------------------------------------------------------------

## 0.2 建立 `docs/upgrade/` Evidence 結構

新增：

``` text
docs/upgrade/
├── README.md
├── baseline.md
├── gates/
├── architecture/
├── test-results/
├── deployment/
├── recovery/
└── hardware/
```

`baseline.md` 至少記錄：

-   commit SHA
-   Python version
-   Node version
-   Docker version
-   Docker Compose version
-   PostgreSQL version
-   OS
-   CPU/RAM
-   GPU/VRAM（若有）
-   test command
-   test result
-   known failures
-   known degraded providers

### Gate 0.2

確認文件存在、沒有 secret、路徑正確。

------------------------------------------------------------------------

## 0.3 跑完整 Baseline Test

不要先改程式。

至少執行 repository 現有的：

``` bash
pytest
npm test / repository-defined frontend checks
docker/scripts/test.sh
docker/scripts/test-ai.sh
```

以及 CI 中實際定義的
backend、PostgreSQL、Redis、frontend、shell/security 檢查。

### Baseline 規則

如果 baseline 本來就紅：

1.  不進 Phase 1。
2.  分類為：
    -   environment failure
    -   flaky test
    -   real regression
    -   missing dependency
    -   hardware-only
3.  先修 baseline。
4.  重新跑。
5.  全部核心 Gate 綠才開始架構升級。

### Gate 0.3

-   [ ] Backend PASS
-   [ ] Frontend PASS
-   [ ] PostgreSQL migration PASS
-   [ ] Redis integration PASS
-   [ ] Core Docker PASS
-   [ ] AI image/import validation PASS
-   [ ] Security baseline PASS

------------------------------------------------------------------------

# 3. Phase 1 --- 測試體系先升級

在改 architecture 前先把「安全網」做厚。

## 1.1 測試分層標準化

測試分類：

``` text
tests/
├── unit/
├── domain/
├── application/
├── contract/
├── integration/
│   ├── postgres/
│   ├── redis/
│   ├── outbox/
│   └── providers/
├── security/
├── migration/
├── e2e/
└── architecture/
```

不一定一次搬所有檔案，但先建立 marker/命名規則。

例如 pytest markers：

``` text
unit
integration
postgres
redis
security
contract
e2e
hardware
slow
```

### Gate 1.1

-   [ ] marker 無 unknown warning
-   [ ] 可以單獨跑 unit
-   [ ] 可以單獨跑 integration
-   [ ] 可以排除 hardware
-   [ ] CI 可明確分 job

------------------------------------------------------------------------

## 1.2 Characterization Tests

針對準備重構的 legacy path，先鎖住現況：

-   Identity login/RBAC
-   Catalog read/availability
-   Cart/checkout
-   Member
-   Campaign
-   Recommendation
-   RAG
-   Voice
-   Emotion
-   Operations

測：

``` text
request
→ status code
→ response schema
→ DB side effect
→ emitted event/outbox
```

### Gate 1.2

在尚未重構前，characterization tests 全綠。

------------------------------------------------------------------------

## 1.3 Contract Snapshot

將 `/api/v1` OpenAPI 產物加入 contract check。

要求：

-   accidental route deletion → fail
-   accidental field rename → fail
-   breaking required-field change → fail
-   legacy `/api/*` 再出現 → fail

### Gate 1.3

-   [ ] `/api/v1` contract stable
-   [ ] `/api/*` forbidden rule PASS
-   [ ] OpenAPI generation deterministic

------------------------------------------------------------------------

# 4. Phase 2 --- Backend 徹底收斂為 Modular Monolith

這是整個升級最重要的 Phase。

目標結構：

``` text
backend/
├── modules/
│   ├── identity/
│   ├── catalog/
│   ├── ordering/
│   ├── member/
│   ├── campaign/
│   ├── recommendation/
│   ├── knowledge/
│   ├── voice/
│   ├── emotion/
│   └── operations/
├── integrations/
├── api/
├── realtime/
└── bootstrap/
```

每個 module 建議：

``` text
module/
├── domain/
│   ├── entities.py
│   ├── value_objects.py
│   ├── policies.py
│   └── events.py
├── application/
│   ├── commands.py
│   ├── queries.py
│   ├── handlers.py
│   └── dto.py
├── ports/
│   ├── repository.py
│   └── providers.py
├── adapters/
│   └── postgres.py
└── public.py
```

不必機械套模板；沒有必要的層不要為了形式建立空檔。

------------------------------------------------------------------------

## 2.1 先建立 Architecture Dependency Test

在搬任何 module 前，先建立規則：

禁止：

``` text
modules/A → modules/B/adapters
modules/A → modules/B/repository
modules/A → routes
domain → FastAPI
domain → SQLAlchemy/psycopg
domain → requests/httpx
domain → Ollama SDK
```

允許：

``` text
route → module public application API
module → own ports
adapter → module ports/domain
module A → module B public API
module A → integration port
```

### Gate 2.1

Architecture test 先對現有違規列 allowlist/baseline，之後 allowlist
只能減少不能增加。

------------------------------------------------------------------------

## 2.2 Identity 收斂

順序：

1.  找出所有 identity route/service/repository caller。
2.  public application API 定義完成。
3.  RBAC policy 移入正確 boundary。
4.  repository implementation 變成 adapter。
5.  route 改呼叫 public API。
6.  compatibility shim caller 歸零。
7.  刪除 shim。

### 測試

-   login success/failure
-   password/session/token path
-   role permission
-   forbidden access
-   device identity
-   tenant/store scope
-   replay/expired credential
-   admin route auth

### Gate 2.2

``` text
Legacy identity callers = 0
Cross-module private import = 0
Identity tests = PASS
Full regression = PASS
```

------------------------------------------------------------------------

## 2.3 Catalog 收斂

雖然 Catalog 已較成熟，仍重新驗證：

-   product
-   category
-   price
-   availability
-   stock/sold-out
-   admin update
-   kiosk read

必須保證 client 不具有 authoritative price。

### Gate 2.3

-   catalog write ownership 唯一
-   server authoritative price
-   kiosk/admin regression PASS
-   PostgreSQL integration PASS

------------------------------------------------------------------------

## 2.4 Ordering 收斂

Ordering 是最高風險 domain。

至少拆出：

``` text
CreateCart
AddItem
UpdateItem
RemoveItem
PriceCart
Checkout
CreateOrder
GetOrder
CancelOrder
PaymentStateTransition
```

Domain invariant：

``` text
client price != trusted price
promotion must be server validated
duplicate checkout must not create duplicate order
AI output cannot mutate authoritative transaction directly
payment pending != paid
```

### 必做測試

-   empty cart
-   invalid product
-   sold-out item
-   price tampering
-   duplicate request
-   idempotency key
-   concurrent checkout
-   DB rollback
-   outbox atomicity
-   AI unavailable
-   Redis unavailable policy
-   payment manual pending

### Gate 2.4

Ordering targeted tests 全綠後，再跑完整 suite；任何 regression
不可進下一項。

------------------------------------------------------------------------

## 2.5 Member 收斂

測：

-   member create/read/update
-   scope isolation
-   duplicate identity
-   points/benefit（若存在）
-   member unavailable 時 checkout policy
-   PII logging protection

### Gate 2.5

Member private repository 不被其他 module import。

------------------------------------------------------------------------

## 2.6 Campaign 收斂

Campaign 不得自行修改 Ordering DB。

應：

``` text
Campaign policy
  ↓
eligible promotion result
  ↓
Ordering validates/applies
```

測：

-   active window
-   expired campaign
-   invalid scope
-   conflicting campaigns
-   client forged discount
-   timezone boundary

------------------------------------------------------------------------

## 2.7 Recommendation 收斂

Recommendation 是 enhancement，不是 transaction authority。

測：

-   provider failure
-   empty recommendation
-   invalid product filtered
-   unavailable product filtered
-   recommendation cannot override price
-   recommendation timeout does not block kiosk

------------------------------------------------------------------------

## 2.8 Knowledge/RAG 收斂

拆：

``` text
Document ingestion
Index lifecycle
Retrieval
Generation adapter
Governance
```

禁止 RAG 直接寫 ordering。

測：

-   ingestion
-   duplicate document
-   index rebuild
-   missing index
-   provider timeout
-   malicious/invalid document handling
-   retrieval result empty
-   Ollama/NIM unavailable

------------------------------------------------------------------------

## 2.9 Voice 收斂

抽象：

``` text
STTPort
TTSPort
```

Voice 只產生 interpretation/input，不直接改 DB。

測：

-   STT timeout
-   malformed audio
-   no speech
-   TTS unavailable
-   cancel
-   concurrent session isolation

------------------------------------------------------------------------

## 2.10 Emotion 收斂

抽象：

``` text
EmotionProvider
```

R1-Omni 是 adapter。

測：

-   provider healthy
-   timeout
-   malformed frame
-   no face/input
-   GPU unavailable
-   model unavailable
-   emotion failure does not block checkout

------------------------------------------------------------------------

## 2.11 Operations 收斂

Operations 負責：

-   health
-   readiness
-   diagnostics
-   provider status
-   version
-   build metadata

不要讓 `/ready` 永遠只回「process alive」。

### Gate 2.11

區分：

``` text
/live = process alive
/ready = core transaction dependencies ready
```

AI degraded 可顯示 degraded，但不應讓 core readiness 失敗，除非
deployment profile 明確要求。

------------------------------------------------------------------------

## 2.12 移除 Legacy Backend

當所有 caller 歸零後才刪：

``` text
legacy services
legacy repositories facade
compatibility shim
dead route
duplicate schema
```

### Phase 2 Final Gate

-   [ ] module ownership matrix PASS
-   [ ] cross-module private import = 0
-   [ ] legacy caller = 0
-   [ ] `/api/*` legacy route = 0
-   [ ] backend full suite PASS
-   [ ] PostgreSQL integration PASS
-   [ ] Redis integration PASS
-   [ ] Docker core PASS

------------------------------------------------------------------------

# 5. Phase 3 --- Persistence 與資料一致性徹底強化

## 3.1 PostgreSQL 唯一商業 authoritative persistence

profiles：

``` text
development → optional test adapters
test        → isolated adapters
pilot       → PostgreSQL required
staging     → PostgreSQL required
production  → PostgreSQL required
```

禁止：

``` text
Postgres failed
→ silently use JSON/SQLite
```

### Gate 3.1

故意給錯 DB URL：

``` text
pilot must fail startup
```

------------------------------------------------------------------------

## 3.2 Migration Discipline

每個 migration：

-   forward-only production policy
-   schema compatibility
-   transaction behavior
-   clean DB test
-   upgrade-from-previous test

CI 建立：

``` text
empty PostgreSQL
→ apply 0001...latest
→ verify schema
```

再：

``` text
previous release schema
→ latest migration
→ smoke test
```

------------------------------------------------------------------------

## 3.3 Constraint 強化

能由 DB 保證的 invariant 不只靠 Python：

-   foreign keys
-   unique constraints
-   not null
-   check constraints
-   scoped uniqueness
-   timestamps
-   state constraints（適合時）

每加一個 constraint 就跑 migration + integration regression。

------------------------------------------------------------------------

## 3.4 Transaction Boundary

特別檢查：

``` text
order + outbox
```

必須同一 transaction。

測：

``` text
order commit + outbox commit
order rollback + no outbox
outbox failure → transaction behavior defined
```

------------------------------------------------------------------------

# 6. Phase 4 --- Worker / Outbox Reliability

## 4.1 Job State Machine

明確：

``` text
pending
processing
succeeded
retry_wait
dead
```

記錄：

-   attempts
-   last_error
-   next_retry_at
-   locked_by
-   locked_at
-   idempotency/dedup key

------------------------------------------------------------------------

## 4.2 Retry Policy

使用 bounded exponential backoff + jitter。

禁止無限快速重試。

測：

-   transient failure
-   permanent failure
-   worker crash
-   retry exhaustion
-   recovery after restart

------------------------------------------------------------------------

## 4.3 Idempotent Consumer

同一 event delivery 兩次，不得：

-   建兩張訂單
-   重複扣庫存
-   重複 payment capture
-   重複 POS submit

### Gate 4.3

duplicate delivery test PASS。

------------------------------------------------------------------------

## 4.4 Dead Letter / Operator Recovery

Admin/ops 至少可看：

-   dead jobs
-   error
-   attempts
-   created time
-   retry action

人工 retry 必須 audit。

------------------------------------------------------------------------

## 4.5 Worker Crash Test

流程：

``` text
enqueue
→ worker processing
→ kill -9 worker
→ restart
→ stale lock recovery
→ eventually succeed exactly once
```

### Phase 4 Gate

Outbox/retry/idempotency/crash/recovery 全綠。

------------------------------------------------------------------------

# 7. Phase 5 --- Frontend 徹底拆分 Kiosk / Admin

## 5.1 建立 Boundary Test

禁止：

``` text
kiosk → admin
admin → kiosk
shared → kiosk
shared → admin
```

shared 只能：

-   API transport
-   auth transport primitives（不含產品 policy）
-   websocket client
-   design tokens
-   stateless UI primitives
-   common utilities

------------------------------------------------------------------------

## 5.2 Kiosk `app.js` 分解

目標：

``` text
frontend/kiosk/
├── app/
├── pages/
├── features/
│   ├── catalog/
│   ├── cart/
│   ├── checkout/
│   ├── member/
│   ├── recommendation/
│   ├── voice/
│   └── emotion/
├── state/
├── components/
└── styles/
```

一次只搬一個 feature。

例如先 Cart：

1.  characterization test
2.  extract cart module
3.  switch import
4.  frontend test
5.  E2E cart test
6.  full regression
7.  commit

再做下一個。

------------------------------------------------------------------------

## 5.3 Admin `admin.js` 分解

目標：

``` text
frontend/admin/
├── app/
├── pages/
├── features/
│   ├── auth/
│   ├── catalog/
│   ├── orders/
│   ├── members/
│   ├── campaigns/
│   ├── recommendation/
│   ├── knowledge/
│   ├── operations/
│   └── settings/
├── state/
└── components/
```

------------------------------------------------------------------------

## 5.4 API Client 收斂

禁止散落：

``` javascript
fetch(...)
```

統一：

``` text
shared/http
→ generated/typed v1 client or explicit API client
```

集中處理：

-   base URL
-   timeout
-   JSON
-   auth
-   request ID
-   error envelope
-   retry policy（僅安全 request）
-   websocket lifecycle

### Gate 5.4

搜尋所有 raw fetch，只有明確 allowlist 可存在。

------------------------------------------------------------------------

## 5.5 CSS Boundary

拆：

``` text
shared/tokens
shared/primitives
kiosk/styles
admin/styles
```

避免 shared stylesheet 同時包含產品專屬 selector。

------------------------------------------------------------------------

## 5.6 Frontend E2E

核心：

``` text
Kiosk:
open → menu → add cart → modify → checkout → confirmation

Admin:
login → catalog change → kiosk reflects change

Failure:
AI down → kiosk still orders
```

### Phase 5 Gate

-   [ ] Kiosk/Admin import boundary PASS
-   [ ] raw fetch policy PASS
-   [ ] frontend full test PASS
-   [ ] core E2E PASS
-   [ ] backend regression PASS

------------------------------------------------------------------------

# 8. Phase 6 --- AI Provider Architecture

## 6.1 LLM Port

建立：

``` text
LLMPort
├── generate()
├── health()
└── metadata()
```

Adapters：

``` text
OllamaAdapter
NvidiaNimAdapter
MockLLMAdapter
```

Domain/application 不知道 provider HTTP URL。

------------------------------------------------------------------------

## 6.2 STT/TTS Port

``` text
STTPort
TTSport
```

明確 timeout、payload size、language、cancellation。

------------------------------------------------------------------------

## 6.3 Emotion Port

``` text
EmotionPort
└── R1OmniAdapter
```

------------------------------------------------------------------------

## 6.4 Circuit Breaker / Timeout / Bulkhead

所有 AI call 必須有：

-   connection timeout
-   total timeout
-   concurrency limit
-   failure classification
-   degraded response

不要讓 AI thread/resource exhaustion 拖死 FastAPI。

------------------------------------------------------------------------

## 6.5 AI Degradation Matrix

建立自動測試：

  Failure        Kiosk Menu   Cart   Checkout   AI Feature
  -------------- ------------ ------ ---------- ------------
  Ollama down    PASS         PASS   PASS       degraded
  R1-Omni down   PASS         PASS   PASS       degraded
  STT down       PASS         PASS   PASS       degraded
  TTS down       PASS         PASS   PASS       degraded
  RAG down       PASS         PASS   PASS       degraded

### Phase 6 Gate

完整 degradation suite PASS。

------------------------------------------------------------------------

# 9. Phase 7 --- Model Registry / Reproducibility

建立：

``` text
config/models/
└── manifest.yaml
```

至少記錄：

``` yaml
models:
  llm:
    provider: ollama
    model: qwen3.5:4b
    digest: "<expected>"
  emotion:
    provider: r1-omni
    model: R1-Omni-0.5B
    revision: "<revision>"
    checksum: "<checksum>"
```

另外記：

-   source
-   license review status
-   required RAM/VRAM
-   local path
-   health command

啟動時驗證必要模型，不允許「名字一樣但內容不明」。

### Gate 7

manifest validation + missing model behavior + checksum/revision policy
PASS。

------------------------------------------------------------------------

# 10. Phase 8 --- Security Hardening

## 8.1 Secrets

禁止：

-   default production password
-   committed `.env`
-   log secret
-   secret in image
-   secret in frontend bundle

Pilot/production 缺 secret → fail closed。

------------------------------------------------------------------------

## 8.2 Container Hardening

保持並驗證：

``` text
non-root
read_only
cap_drop ALL
no-new-privileges
tmpfs
minimal writable mounts
```

新增 automated assertions。

------------------------------------------------------------------------

## 8.3 Network Exposure

預設：

``` text
127.0.0.1
```

LAN 才明確開：

``` text
0.0.0.0
```

PostgreSQL/Redis/Ollama/R1 service 不應無理由直接暴露到 LAN。

------------------------------------------------------------------------

## 8.4 CORS / Security Headers

production profile：

-   explicit origin
-   CSP（依前端需求）
-   frame policy
-   content type
-   referrer policy
-   cache policy for sensitive admin response

------------------------------------------------------------------------

## 8.5 Auth/RBAC

測：

-   horizontal privilege escalation
-   vertical privilege escalation
-   store scope
-   device scope
-   expired auth
-   revoked auth
-   admin-only endpoints

------------------------------------------------------------------------

## 8.6 Rate Limit

至少：

-   login
-   expensive RAG/LLM
-   STT upload
-   emotion frames
-   sensitive admin write

Redis unavailable 時 production policy 必須明確，不可無聲失去保護。

------------------------------------------------------------------------

## 8.7 Upload Security

RAG/媒體上傳：

-   MIME validation
-   size limit
-   filename normalization
-   path traversal
-   extension mismatch
-   object key isolation

### Phase 8 Gate

security suite + container assertions + secret scan PASS。

------------------------------------------------------------------------

# 11. Phase 9 --- Observability / Operations

## 9.1 Structured Logging

統一欄位：

``` text
timestamp
level
service
version
request_id
trace_id
store_id
device_id
module
event
duration_ms
error_code
```

禁止記：

-   password
-   token
-   full payment secret
-   unnecessary member PII
-   raw sensitive audio/image unless explicitly governed

------------------------------------------------------------------------

## 9.2 Build Metadata Endpoint

提供：

``` text
version
git_sha
build_time
schema_version
deployment_profile
```

不暴露 secret。

------------------------------------------------------------------------

## 9.3 Health Model

``` text
/live
/ready
/api/v1/operations/status
```

區分：

-   core ready
-   DB
-   Redis
-   worker
-   outbox backlog
-   object storage
-   LLM
-   RAG
-   STT
-   TTS
-   emotion

AI 可是：

``` text
DEGRADED
```

核心仍可：

``` text
READY
```

------------------------------------------------------------------------

## 9.4 Metrics

至少收：

-   request count
-   latency
-   5xx
-   checkout success/failure
-   DB latency
-   worker backlog
-   retry count
-   dead jobs
-   AI latency/error
-   websocket sessions
-   disk usage
-   backup age

### Phase 9 Gate

故意製造錯誤，確認 logs/metrics/status 能定位原因。

------------------------------------------------------------------------

# 12. Phase 10 --- Backup / Restore / Disaster Recovery

「有 backup script」不算完成；**成功 restore 才算完成。**

## 10.1 Backup Scope

備份：

``` text
PostgreSQL
object storage
RAG metadata/index metadata as required
configuration excluding replaceable secrets
release manifest
model manifest
```

模型權重與 immutable image 原則上可重新取得，不必當主要業務資料備份。

------------------------------------------------------------------------

## 10.2 PostgreSQL Backup

建立：

``` text
scripts/backup/
├── backup_postgres.sh
├── backup_objects.sh
├── verify_backup.sh
└── restore_test.sh
```

輸出帶：

``` text
timestamp
schema version
app version
checksum
```

------------------------------------------------------------------------

## 10.3 Restore Drill

測試：

``` text
建立真實測試資料
→ backup
→ destroy test DB
→ fresh PostgreSQL
→ restore
→ start app
→ verify member/catalog/order
→ verify checksum/count
→ run checkout smoke
```

### Gate 10.3

Restore drill PASS 才算 backup 完成。

------------------------------------------------------------------------

## 10.4 Retention

建議起點：

``` text
7 daily
4 weekly
3 monthly
```

實際 retention 再依商業/法規需求調整。

------------------------------------------------------------------------

# 13. Phase 11 --- Release Engineering

## 11.1 Semantic Version

使用：

``` text
v1.0.0
v1.0.1
v1.1.0
```

main 不直接代表現場版本。

------------------------------------------------------------------------

## 11.2 Immutable Image

Release 必須使用：

``` text
project2026-app:<version>
project2026-worker:<version>
```

並記 image digest。

不要現場：

``` text
git pull main
docker build
```

------------------------------------------------------------------------

## 11.3 Release Manifest

每版：

``` yaml
version: 1.0.0
git_sha: ...
schema_version: 0021
images:
  app:
    digest: sha256:...
  worker:
    digest: sha256:...
models:
  manifest_version: ...
minimum_hardware: ...
```

------------------------------------------------------------------------

## 11.4 CI Release Gate

Tag 前/後：

``` text
lint
unit
domain
contract
PostgreSQL
Redis
migration
outbox
security
frontend
E2E
Docker
SBOM
image scan
```

任一 fail → 不發布。

------------------------------------------------------------------------

## 11.5 SBOM / Dependency Audit

對 Python、Node、container 產生可追蹤 dependency inventory。

高風險 vulnerability 不應無紀錄直接 release。

------------------------------------------------------------------------

# 14. Phase 12 --- Deployment Appliance

目標不是「使用者會 Docker」，而是設備開機就能工作。

## 12.1 Host 標準化

首要 production target 建議固定：

``` text
Debian/Ubuntu LTS
Docker Engine
Docker Compose plugin
systemd
Chromium
```

macOS/Windows 保留 development compatibility，不把三平台同時當正式
appliance target。

------------------------------------------------------------------------

## 12.2 Directory Layout

例如：

``` text
/opt/project2026/
├── releases/
├── current/
├── config/
└── scripts/

/var/lib/project2026/
├── postgres/
├── objects/
├── rag/
├── backups/
└── logs/
```

------------------------------------------------------------------------

## 12.3 systemd

建立：

``` text
project2026.service
project2026-kiosk.service
project2026-backup.timer
```

流程：

``` text
boot
→ docker ready
→ compose up
→ /ready PASS
→ chromium --kiosk
```

------------------------------------------------------------------------

## 12.4 Kiosk Browser

要求：

-   full screen
-   no browser chrome
-   restart on crash
-   controlled cache
-   reconnect after backend restart
-   friendly unavailable screen
-   no access to OS desktop for normal user

------------------------------------------------------------------------

## 12.5 Installer

建立 idempotent installer：

``` bash
sudo ./install.sh
```

應完成：

-   prerequisite check
-   directory
-   service account
-   Docker
-   config template
-   secret check
-   release install
-   systemd
-   health verification

重跑不應破壞資料。

### Gate 12.5

在 fresh VM 執行完整安裝，不使用開發機殘留環境。

------------------------------------------------------------------------

# 15. Phase 13 --- Update / Rollback

## 13.1 更新流程

``` text
download release
→ verify checksum/signature
→ backup
→ pull image
→ preflight
→ migration
→ start new version
→ readiness
→ smoke
→ mark active
```

------------------------------------------------------------------------

## 13.2 Rollback 分類

必須分：

### Application rollback

舊 image 重新啟動。

### Database rollback

不能假設 migration 可以隨意 down。

因此 migration 設計需考慮 expand/contract：

``` text
Release N:
add nullable/new structure

Release N+1:
code switches

Release N+2:
remove old structure
```

避免一版 migration 直接讓前一版完全不能啟動。

------------------------------------------------------------------------

## 13.3 自動失敗處理

若新版本：

``` text
/ready fail
core smoke fail
```

部署腳本不得宣告成功。

應：

``` text
stop new
→ restore compatible previous app
→ operator alert/log
```

涉及不可逆 DB migration 時，不做虛假的「自動 DB rollback」，而採相容
migration + recovery procedure。

### Phase 13 Gate

實際部署一個故意失敗版本，證明 rollback 流程有效。

------------------------------------------------------------------------

# 16. Phase 14 --- Payment / POS 正式邊界

## 14.1 Payment Port

``` text
PaymentPort
├── create_intent
├── authorize
├── capture
├── cancel
├── refund
└── get_status
```

manual adapter 保留作為：

``` text
ManualPaymentAdapter
```

未來廠商：

``` text
VendorPaymentAdapter
```

Ordering 只認 domain result。

------------------------------------------------------------------------

## 14.2 Payment State Machine

明確：

``` text
pending
authorized
paid
failed
cancelled
refunded
```

禁止：

``` text
HTTP 200 = paid
```

------------------------------------------------------------------------

## 14.3 Webhook Idempotency

外部 payment webhook：

-   signature validation
-   timestamp/replay policy
-   event id dedup
-   state transition validation
-   audit log

------------------------------------------------------------------------

## 14.4 POS Port

``` text
POSPort
├── submit_order
├── get_status
├── cancel
└── health
```

使用 outbox 非同步送單。

POS 掛掉不應遺失已完成的本地訂單。

### Phase 14 Gate

先用 fake/manual adapter 完整模擬成功、timeout、duplicate、late
callback、failure，再接真廠商。

------------------------------------------------------------------------

# 17. Phase 15 --- Admin AI Content Agent

AI 不直接修改 production truth。

架構：

``` text
Data/analytics
    ↓
AI Agent
    ↓
Proposal
    ↓
Validation
    ↓
Draft
    ↓
Admin Review
    ↓
Approve
    ↓
Publish command
    ↓
Domain validation
    ↓
DB
```

Proposal 必須記：

-   generated_by
-   model/version
-   source/context
-   before
-   proposed after
-   reason
-   risk
-   created_at
-   approved_by
-   approved_at

### Gate 15

測：

-   AI hallucinated product ID → reject
-   invalid price → reject
-   unauthorized admin → reject
-   model unavailable → no production change
-   approval → audited publish
-   reject → no production change

------------------------------------------------------------------------

# 18. Phase 16 --- Performance / Load / Concurrency

建立明確 SLO 起始值，不要只說「感覺很快」。

測：

-   catalog p95
-   cart p95
-   checkout p95
-   admin reads
-   websocket
-   worker throughput
-   AI latency 分開統計

## Concurrency Scenarios

-   同 device double click checkout
-   多 browser 同時下單
-   admin 改 availability 同時 kiosk checkout
-   worker 多 instance claim job
-   Redis lock contention

### Gate 16

沒有 duplicate order、corrupt state、deadlock、unbounded latency。

------------------------------------------------------------------------

# 19. Phase 17 --- Failure Injection

必做 Chaos/Failure Matrix：

``` text
PostgreSQL restart
Redis restart
worker kill
app restart
Ollama kill
R1 kill
network disconnect
disk nearly full
invalid secret
corrupt/missing model
expired auth
object storage unavailable
```

每項定義：

``` text
expected behavior
observed behavior
recovery procedure
data loss = yes/no
```

核心原則：

``` text
AI failure → degraded
DB failure → fail safe
payment ambiguity → pending/unknown, never fake paid
worker failure → recoverable
```

------------------------------------------------------------------------

# 20. Phase 18 --- Hardware Pilot

這是從 Software Project 變 Product 的 Gate。

## 18.1 Fresh Device Test

禁止用日常開發機當證據。

新設備：

``` text
OS install
→ installer
→ model provisioning
→ restore/config
→ boot
→ kiosk
```

------------------------------------------------------------------------

## 18.2 Peripheral Test

依實際硬體：

-   touchscreen
-   microphone
-   speaker
-   camera
-   printer
-   scanner
-   payment terminal

------------------------------------------------------------------------

## 18.3 Burn-In

第一階段至少：

``` text
8 hours
```

再做：

``` text
24 hours
```

期間週期性：

-   menu read
-   cart
-   checkout
-   AI request
-   admin operation
-   worker
-   backup

監控：

-   RAM
-   VRAM
-   disk
-   CPU/GPU temperature
-   process restart
-   DB connections
-   websocket leaks
-   AI memory growth

------------------------------------------------------------------------

## 18.4 Power Loss

在測試環境：

``` text
transaction idle
transaction active
worker active
```

模擬非正常斷電/強制停止後重新開機。

確認：

-   PostgreSQL recovery
-   no duplicate checkout
-   outbox recovery
-   systemd restart
-   kiosk auto launch

------------------------------------------------------------------------

## 18.5 Network Loss

若 Local-First：

網際網路中斷後應確認：

-   core menu PASS
-   cart PASS
-   checkout PASS（依 payment 模式）
-   local Ollama PASS
-   local R1 PASS
-   Edge TTS 若依賴網路 → degraded
-   cloud NIM → degraded

------------------------------------------------------------------------

# 21. Phase 19 --- Commercial Pilot Gate

不要用「功能看起來完成」宣告 Pilot Ready。

建議最低 evidence：

``` text
Fresh install: PASS
Cold boot: PASS
Restart: PASS
Backup: PASS
Restore: PASS
Update: PASS
Rollback: PASS
AI degradation: PASS
DB recovery: PASS
Worker recovery: PASS
Security gate: PASS
8h burn-in: PASS
24h burn-in: PASS
100+ synthetic/controlled orders: PASS
No duplicate authoritative orders
No silent data loss
```

再進實店 controlled pilot。

------------------------------------------------------------------------

# 22. Phase 20 --- 實店 Pilot

先 controlled rollout，不直接 full production。

## Day 0

-   backup verified
-   release pinned
-   hardware health
-   admin credential
-   recovery USB/installer
-   rollback version
-   support runbook

## Pilot 期間追蹤

-   order count
-   checkout failures
-   abandoned carts
-   AI failure rate
-   STT failure
-   emotion latency
-   worker retries
-   dead jobs
-   operator interventions
-   device restart
-   disk growth

每個 incident 都建立：

``` text
timestamp
version
symptom
root cause
fix
test added?
regression prevented?
```

**沒有補 regression test 的 bug 不算完整修復。**

------------------------------------------------------------------------

# 23. CI/CD 最終建議流水線

``` text
PR
│
├─ formatting/lint
├─ architecture rules
├─ unit/domain
├─ API contract
├─ frontend
├─ security
└─ fast integration
      │
      ▼
Merge main
│
├─ PostgreSQL
├─ Redis
├─ migration
├─ outbox
├─ E2E
├─ Docker core
└─ AI build/import
      │
      ▼
Release Tag
│
├─ all previous gates
├─ dependency audit
├─ SBOM
├─ image scan
├─ immutable images
├─ release manifest
└─ checksums
      │
      ▼
Staging Appliance
│
├─ deploy
├─ migration
├─ smoke
├─ failure test subset
└─ rollback verification
      │
      ▼
Pilot
```

------------------------------------------------------------------------

# 24. 每個項目的標準工作模板

未來任何 Issue 都使用以下模板：

``` markdown
# ITEM-X

## Objective
本項目唯一要完成的目標。

## Scope
允許修改的範圍。

## Non-goals
本項目刻意不做什麼。

## Baseline
修改前測試與 commit。

## Change
實作內容。

## Targeted Tests
與本修改直接相關的測試。

## Regression Tests
可能被影響的既有功能。

## Failure Test
刻意破壞 dependency 時的預期行為。

## Evidence
command、result、log/artifact。

## Exit Criteria
所有條件都 PASS。

## Commit
commit SHA。
```

------------------------------------------------------------------------

# 25. 每項修改後固定測試順序

依修改類型裁切，但順序不變：

``` text
1. Syntax / format
2. Static / architecture
3. Unit
4. Domain/application
5. Contract
6. Integration
7. Security
8. Frontend
9. E2E
10. Docker
11. Failure/degradation
12. Full regression
```

如果第 4 步失敗：

``` text
不要跑第 5~12 步假裝收集更多結果
```

先修第 4 步，再從本項必要 Gate 重新開始。

------------------------------------------------------------------------

# 26. 禁止事項

升級期間禁止以下做法：

1.  為了綠 CI 而 skip 真正失敗測試。
2.  把 production failure 改成 silent fallback。
3.  AI 直接寫 authoritative order/payment。
4.  frontend 決定 authoritative price/discount/payment。
5.  route 直接操作其他 module repository。
6.  新增 legacy `/api/*`。
7.  現場設備 `git pull main` 當正式升級。
8.  使用 `latest` 當唯一 production image tag。
9.  migration 未測就部署。
10. backup 未 restore 過就宣稱可復原。
11. AI health fail 就讓整個 kiosk 不能點餐。
12. payment timeout 就猜測成功。
13. 把 secret 放 image/repository/frontend。
14. 一次重構多個 module 後才測試。
15. 「先全部改完再一起 debug」。

------------------------------------------------------------------------

# 27. 推薦實際執行順序

嚴格依序：

``` text
00 Baseline
01 Test Infrastructure
02 Architecture Dependency Rules
03 Identity
04 Catalog
05 Ordering
06 Member
07 Campaign
08 Recommendation
09 Knowledge/RAG
10 Voice
11 Emotion
12 Operations
13 Remove Backend Legacy
14 PostgreSQL Hardening
15 Migration Hardening
16 Outbox/Worker Reliability
17 Kiosk Frontend Decomposition
18 Admin Frontend Decomposition
19 Shared/API Client Cleanup
20 Frontend E2E
21 AI Provider Ports
22 AI Degradation
23 Model Registry
24 Security
25 Observability
26 Backup
27 Restore Drill
28 Release Engineering
29 Immutable Images
30 Appliance Installer
31 systemd/Kiosk Mode
32 Update
33 Rollback
34 Payment Port
35 POS Port
36 Admin AI Proposal Workflow
37 Performance
38 Concurrency
39 Failure Injection
40 Fresh Hardware Install
41 8h Burn-In
42 24h Burn-In
43 Commercial Pilot Gate
44 Controlled Store Pilot
45 Commercial V1 Release
```

**不要交換高風險依賴順序。**

例如不要在 Ordering 還沒收斂時先做真實 Payment integration。

------------------------------------------------------------------------

# 28. 最終 Commercial V1 Definition of Done

只有以下全部成立，才將 README 的狀態從：

``` text
local pilot / NOT_READY
```

改成正式的 Commercial V1/Pilot Certified 狀態：

## Architecture

-   [ ] Backend modules fully converged
-   [ ] Cross-module private imports = 0
-   [ ] Legacy service/repository compatibility path = 0
-   [ ] Kiosk/Admin boundaries enforced
-   [ ] AI provider ports established

## Data

-   [ ] PostgreSQL authoritative
-   [ ] migrations reproducible
-   [ ] constraints verified
-   [ ] outbox atomic
-   [ ] duplicate processing idempotent

## Core Product

-   [ ] menu
-   [ ] cart
-   [ ] checkout
-   [ ] order
-   [ ] admin
-   [ ] member
-   [ ] campaign
-   [ ] recommendation

## AI

-   [ ] LLM degraded safely
-   [ ] RAG degraded safely
-   [ ] STT degraded safely
-   [ ] TTS degraded safely
-   [ ] R1-Omni degraded safely
-   [ ] model manifest reproducible

## Security

-   [ ] no default production secret
-   [ ] RBAC verified
-   [ ] rate limits verified
-   [ ] container hardening verified
-   [ ] upload security verified
-   [ ] secret scan clean

## Operations

-   [ ] `/live`
-   [ ] `/ready`
-   [ ] diagnostic status
-   [ ] structured logs
-   [ ] metrics
-   [ ] worker visibility
-   [ ] dead job recovery

## Recovery

-   [ ] backup automatic
-   [ ] backup verified
-   [ ] restore drill PASS
-   [ ] update PASS
-   [ ] rollback PASS

## Deployment

-   [ ] versioned immutable release
-   [ ] fresh machine install PASS
-   [ ] auto startup
-   [ ] kiosk auto launch
-   [ ] watchdog/restart
-   [ ] release manifest
-   [ ] image digest/SBOM

## Hardware

-   [ ] peripherals PASS
-   [ ] offline/degraded mode PASS
-   [ ] restart PASS
-   [ ] power-loss recovery PASS
-   [ ] 8h burn-in PASS
-   [ ] 24h burn-in PASS

## Pilot

-   [ ] controlled order volume PASS
-   [ ] no silent data loss
-   [ ] no duplicate authoritative checkout
-   [ ] incident runbook ready
-   [ ] rollback package ready

------------------------------------------------------------------------

# 29. 專案完成後的目標結構

``` text
Project_2026/
├── .github/
│   └── workflows/
├── config/
│   ├── profiles/
│   └── models/
├── docker/
│   ├── compose.yaml
│   ├── compose.ai.yaml
│   ├── compose.ai-gpu.yaml
│   └── compose.pilot.yaml
├── docs/
│   ├── architecture/
│   ├── operations/
│   ├── security/
│   ├── recovery/
│   ├── deployment/
│   └── upgrade/
├── UI_API/
│   ├── backend/
│   │   ├── api/
│   │   ├── modules/
│   │   ├── integrations/
│   │   ├── realtime/
│   │   └── bootstrap/
│   ├── frontend/
│   │   ├── kiosk/
│   │   ├── admin/
│   │   └── shared/
│   └── tests/
├── scripts/
│   ├── install/
│   ├── backup/
│   ├── restore/
│   ├── deploy/
│   └── rollback/
├── R1-Omni/
└── release/
```

`services/`、legacy repository facade 等只有在所有 caller
歸零、測試通過後才移除；不要為了「目錄看起來漂亮」提前刪除。

------------------------------------------------------------------------

# 30. 最終架構原則

整個 Project_2026 最終應遵守：

``` text
             ┌─────────────┐
             │    Kiosk    │
             └──────┬──────┘
                    │
             ┌──────▼──────┐
             │   API v1    │
             └──────┬──────┘
                    │
       ┌────────────▼────────────┐
       │  Application Modules    │
       │                         │
       │ Identity / Catalog      │
       │ Ordering / Member       │
       │ Campaign / Knowledge    │
       │ Recommendation          │
       │ Voice / Emotion / Ops   │
       └────────────┬────────────┘
                    │
             Ports / Events
                    │
       ┌────────────┼─────────────┐
       ▼            ▼             ▼
 PostgreSQL       Worker       Integrations
                    │             │
                  Outbox      ┌────┼─────┐
                              ▼    ▼     ▼
                            LLM  Voice Emotion
```

其中：

``` text
Ordering + PostgreSQL
        =
Transaction Authority
```

而：

``` text
LLM / RAG / Voice / Emotion
        =
Enhancement Layer
```

這條界線在任何未來功能中都不得被破壞。

------------------------------------------------------------------------

# 31. 執行策略總結

這次升級不是：

``` text
找 20 個問題
→ 一次全部改
→ 最後 pytest
→ 修到能跑
```

而是：

``` text
Baseline
   ↓
建立測試安全網
   ↓
建立 architecture rules
   ↓
一次收斂一個 domain
   ↓
每個 domain 全測
   ↓
資料層
   ↓
worker/outbox
   ↓
frontend
   ↓
AI adapters
   ↓
security
   ↓
observability
   ↓
backup/restore
   ↓
release
   ↓
appliance
   ↓
update/rollback
   ↓
payment/POS
   ↓
performance/failure injection
   ↓
fresh hardware
   ↓
burn-in
   ↓
controlled pilot
   ↓
Commercial V1
```

**前一 Gate 沒過，下一 Gate 不開始。**

這是本計畫最重要的執行規則。

------------------------------------------------------------------------

# 32. 第一個實際工作

不要從「重構 Ordering」直接開始。

第一個工作應是：

``` text
UPGRADE-000
Freeze and Prove Baseline
```

完成：

1.  建 `upgrade/commercial-v1`。
2.  記錄 baseline SHA。
3.  建 `docs/upgrade/`。
4.  跑目前所有核心 CI/test。
5.  修到 baseline 全綠。
6.  保存 test evidence。
7.  commit。
8.  才開始 `UPGRADE-001 Test Infrastructure`。

這樣後面每一次架構修改都能回答一個關鍵問題：

> **「這次修改是否真的讓 Project_2026
> 變得更好，而且沒有破壞上一個已驗證狀態？」**

只有答案可以被測試證據證明為「是」，才進下一項。
