# 現況架構

狀態：已接受為 Milestone 0 架構基線
最後盤點：2026-07-13

## 系統範圍

目前主要產品位於 `UI_API/`，由一個 FastAPI application 同時提供：

- `/kiosk` 顧客自助點餐頁面。
- `/admin` 營運管理頁面。
- 既有 `/api/*` Form/JSON API。
- `/ws/{client_type}/{session_id}` WebSocket。
- 會員、菜單、結帳、活動、推薦、互動、RAG、語音與情緒分析流程。

Emotion-LLaMA 與 R1-Omni 已是獨立 process，但 API 對其依賴仍由 application service 直接組合。

## Runtime Topology

```text
Browser: Kiosk ───────┐
                      ├── FastAPI app ── JSON files / PostgreSQL
Browser: Admin ───────┤        │
                      │        ├── Ollama / Gemini
WebSocket clients ────┘        ├── STT / TTS provider
                               ├── Chroma / embedding model
                               └── Emotion-LLaMA / R1-Omni HTTP gateway
```

開發入口 `main.py` 會以 thread 啟動兩個 Uvicorn server，預設使用 9000 與 9001。兩個 server 共用同一個 application object 與 module singleton；這是開發便利方案，不是 production deployment model。

## Backend Composition

```text
main.py
  └── app_factory.create_app
       ├── middleware / static files / lifespan
       └── api.router.register_routes
            └── api.route_registry.ROUTE_REGISTRY
                 └── 14 個 route module / 75 個 HTTP 或 WebSocket route
```

主要依賴方向已形成：

```text
routes → services → repositories
```

但目前仍有過渡性例外：

- `core_routes`、`menu_routes`、`interaction_routes`、`recommendation_event_routes` 等直接呼叫 repository。
- `rag_routes` 直接取得 RAG provider。
- `rag_document_service`、`rag_review_service`、`rag_alert_service`、`observability_service` 直接操作檔案系統。
- Service 間有大量同步呼叫，尚未以 module facade 或 domain event 隔離。
- 跨層 request/response 仍大量使用 `dict`；Route 內至少有 15 個大型 raw JSON body contract。

## Business Flow Map

### Kiosk Checkout

```text
kiosk app/cart
  → POST /api/checkout (legacy Form API)
  → checkout_pricing_service
  → checkout_service
  → log/session repositories
  → member/recommendation event services
```

Server 已重新驗證菜單價格、數量與促銷資格；舊 Form contract 必須保留至 `/api/v1` JSON contract 穩定後。

### Member

```text
member routes
  → member_service
  → member_repository + member_session_repository
  → JSON 或 PostgreSQL adapter
```

目前 phone 同時是登入識別、repository lookup key 與 PostgreSQL primary key。登入沒有 OTP/PIN，是已知 commercial blocker。

### Recommendation / Promotion

推薦上下文由會員偏好、熱門度、供應狀態、活動、RAG offer、實驗與回饋等 service 聚合。活動資料以版本化 JSON 文件管理，checkout 會再次驗證活動規則。

### RAG

RAG 文件、審核佇列、告警、rebuild status 與 Chroma index 分散在版本化文件和 runtime JSON/Chroma。Rebuild 在 API process 內執行，尚未交給 worker；多 instance 同時 rebuild 沒有 distributed lock。

### Voice / AI / Emotion

- `ai_services.py` 直接實作 Ollama/Gemini request、retry 與 JSON repair。
- STT/TTS 有抽象基底與 factory，但 provider 與設定仍在同一 module。
- Emotion service 直接使用 HTTP client 呼叫 Emotion-LLaMA/R1-Omni，並在 process memory 保存 session cache。
- RAG provider 使用 class-level singleton 保存 embedding、Chroma 與 BM25 state。

## Data Boundaries

目前資料來源：

| 資料 | Current source | 主要限制 |
| --- | --- | --- |
| Menu | JSON | 無 tenant/store version |
| Member | JSON / PostgreSQL | phone PK、PII 未加密 |
| Member session | process/JSON compatibility / PostgreSQL | device scope 不明確 |
| Recommendation events | JSON / PostgreSQL | tenant/store/device 欄位缺失 |
| RAG source | Files | 發布與 rebuild 同 process |
| RAG vector | Chroma local directory | 無 shared object/vector storage |
| WebSocket connection | Process memory | 無跨 instance fan-out |
| Voice history | Process memory | restart 遺失、多 worker 分裂 |
| Settings | environment + tracked/default JSON compatibility | infrastructure/business config 混合 |

PostgreSQL migration 已有 version、checksum 與 `schema_migrations`，但 schema timestamp 多為 `TEXT`，且目前只涵蓋會員、推薦事件與 audit 的部分商業資料。

## Frontend Boundaries

- Kiosk 與 Admin 沒有互相 import，這是可保留的良好邊界。
- `frontend/shared` 提供 HTTP、API、realtime 與 UI helper，但仍混有 Kiosk credential handling 與 application-specific API。
- Kiosk 以 module-level mutable state 與 runtime dependency registry 協作。
- Admin 仍有大量 feature logic 與 raw `fetch` 集中在單一檔案。
- 現有 TypeScript `checkJs` 僅覆蓋部分 shared/kiosk modules，尚未覆蓋 `admin.js` 與 `kiosk/app.js`。

大型檔案基線：

| File | Lines |
| --- | ---: |
| `frontend/admin/admin.js` | 2,238 |
| `frontend/kiosk/app.js` | 2,199 |
| `backend/services/member_service.py` | 776 |
| `backend/services/rag_document_service.py` | 472 |
| `backend/services/recommendation_event_service.py` | 407 |

## Maintainability Audit

### Circular dependency

目前靜態 import graph 沒有確認到 repository → service/route 或 route/service 的直接循環；repository 仍維持向下依賴。不過下列 function-local import 顯示 service boundary 已靠延遲 import 避免載入順序問題，後續應以 module facade 或 port 解耦：

- `rag_review_service` → `rag_document_service`。
- `voice_service` → `emotion_service`。
- `emotion_service` → `intervention_pipeline_service`。

這些項目是高耦合候選，不在 Milestone 0 改寫。

### Dead-code candidates

靜態引用盤點找到下列無 consumer 或無實際用途的候選：

- `realtime/event_bus.py::EVENT_TYPES` 只有宣告，沒有 validation 或其他引用。
- `RouteRegistration.group` 有填值，但 route registration 流程沒有讀取。
- `createCartManager` 的 `lang` option 由 `kiosk/app.js` 傳入，但 cart implementation 沒有使用。

FastAPI decorators、DOM inline handler、dynamic module 與模型 adapter 會讓純靜態 caller count 產生誤判，因此上述項目只登記為候選；刪除前必須補測試並在單獨 PR 驗證，不在 Milestone 0 移除。

### Duplicate logic

- Admin credential/header 組裝同時存在於 `frontend/admin/admin.js` 與 `frontend/shared/apiClient.js`。
- `_safe_text`、`_safe_text_list` 與 `_as_optional_int` 類 validation helper 分散在 recommendation、promotion、RAG 等多個 service，且限制值不一致。
- JSON file read/write、atomic replace 與 lock pattern 分散於多個 repository/service。

這些重複不宜直接合併成無邊界的 global utility；應隨 domain module 遷移，將共通 infrastructure primitive 與 domain validation 分開。

## Operational Baseline

已存在：

- 155 個 pytest（包含 5 個 Commercial Foundation governance regression tests）。
- production route flag gating、token boundary、rate limit 與基本安全 headers。
- PostgreSQL backup/restore shell scripts。
- structured request log 與 Admin health summary。
- 模型權重、runtime data 與 Secret 的 Git ignore 規則。
- CPU-only CI dependency profile、GitHub Actions workflow 與 frontend lockfile。
- Ruff lint/format、14 個漸進式 mypy source file 與 frontend TypeScript `checkJs` gate。

缺少：

- Production Docker/image/compose/nginx baseline。
- 公開 liveness 與 dependency-aware readiness contract。
- Redis/worker/distributed lock。
- Multi-tenant identity、RBAC 與 device credential rotation。
- E2E Kiosk/Admin smoke test。
- 可演練的 deploy rollback 與 restore validation runbook。

## Audit Baseline

Milestone 0 修改前基線：

- Backend pytest：150 passed，1 dependency deprecation warning。
- Frontend syntax：passed。
- Frontend typecheck：not runnable，缺少 lockfile/installed TypeScript。
- Shell syntax：passed。
- Tracked model weights：none detected。
- Filled tracked API secrets：none detected in configured settings baseline。

Milestone 0 完成驗證：

- Backend pytest：155 passed，1 dependency deprecation warning。
- Ruff lint/format 與漸進式 mypy：passed。
- Frontend clean install、typecheck 與 syntax：passed。
- Shell syntax、CI YAML、App import 與 `/kiosk`/`/admin` smoke：passed。
- CI candidate files 未偵測 Secret signature 或 tracked model weights。

此現況作為後續 ADR 與 milestone 的比較基準；README 與本文件若和程式碼衝突，以程式碼與 migration 為準。
