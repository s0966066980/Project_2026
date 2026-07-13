# 後續模組規劃

- 文件版本：1.0
- 狀態：Active
- 最後更新：2026-07-13

本文件只保存尚未完成或正在演進的跨模組工作。已完成項目應移除或改寫到對應 README/架構文件，不長期保留成「完成清單」。

優先級：

- `P0`：商用前阻斷或重大風險。
- `P1`：商用試點與維運效率的重要能力。
- `P2`：擴充、最佳化或規模化能力。

## Roadmap

| 優先級 | 模組 | 目標 | 主要依賴 | 完成條件 |
| --- | --- | --- | --- | --- |
| P0 | Member UUID / PII contract phase | 移除已驗證無使用者的 phone compatibility column | 1F production metrics、法務/隱私審查 | uuid_only 穩定、rotation/recovery 演練、forward contract migration |
| 完成 | Order outbox consumption | 可靠發布 Order lifecycle event | 1G transactional outbox、Worker | retry、backoff、dead letter、idempotent delivery、backlog metrics 已建立；外部 sink 後續擴充 |
| P1 | External telemetry backend | 將既有 metrics/trace contract 接到 deployment backend | 1H observability contract、Deployment | exporter、dashboard、paging、retention、實測 SLO report |
| 完成 | API v1 contracts | typed、versioned read surface | Pydantic/OpenAPI | `/api/v1`、統一 error、相容層已建立；write caller 逐步遷移 |
| 完成 | Frontend toolchain | Kiosk/Admin multi-entry build 與測試基線 | API contracts | Vite、TypeScript、Vitest、Playwright 已納入 CI |
| 完成 | Frontend feature modules baseline | bounded extraction 與 boundary enforcement | Frontend toolchain | Kiosk bootstrap/Admin auth 已抽離，既有 feature modules 與 E2E 保持；後續逐 feature 演進 |
| 完成 | Redis shared infrastructure | multi-instance ephemeral coordination | Deployment | scoped rate limit/cache/lock adapter 與 fail-closed policy 已建立 |
| 完成 | Worker | 移出長時間與可重試工作 | PostgreSQL job/outbox | durable job contract、retry/DLQ、outbox consumer 與 metrics 已建立；RAG rebuild 等 handler 後續接上 |
| 完成（內部） | LLM Gateway cutover | 標準化文字生成 Provider | Port/Adapter | 5C：Production callers 經 Gateway；timeout budget 真實有效；task schema；adapter-only ai_services |
| 完成（內部） | Emotion Gateway cutover | 隔離 GPU 模型 runtime | Port/Adapter | 5D：主 Emotion 流程經 Multimodal Gateway；adapter-only `/predict`；no-evidence safe |
| 完成（內部） | RAG governance durable | 文件版本、審核、發布與 rollback | Worker / Object Storage | 6A：PostgreSQL metadata + object content_ref + rebuild side effect；JSON 僅相容 |
| 完成 | Promotion / Recommendation governance | 策略版本與成效治理 | Event data | strategy lifecycle、eligibility、experiment assignment、event quality 已建立 |
| 完成（內部） | Object Storage truthfulness | 管理文件、音訊、影片與匯出物 | Security/Privacy | 5B：HMAC signed access、local disk、truthful encryption metadata、PG metadata；雲端 S3/KMS wiring 仍 EXTERNAL_BLOCKED（10B） |
| 完成 | POS / Payment adapters | 串接正式交易系統 | Order state machine | fake/sandbox contract、webhook、reconciliation 已建立；真實商戶認證 BLOCKED |
| 完成 | Fleet management | 管理大量 Kiosk | Device identity | heartbeat、allowlisted command、rollout ring 基線已建立 |
| 完成 | Data analytics pipeline | 建立營運與推薦分析 | Event contract | envelope、idempotent publish/replay、quality counters 已建立 |
| 完成 | Multi-region / HA evaluation | 評估大規模可用性 | SLO、observability | ADR-0010 依證據 defer multi-region / active-active |

## 建議執行順序

### Phase 1：商用資料與權限基礎

1. 完成 Tenant / Store / Device enforcement（foundation 已建立）。
2. Member UUID / PII。
3. Order / Checkout hardening。

### Phase 2：工程化與營運

1. Frontend toolchain 與 feature modules — 完成。
2. Redis shared infrastructure — 完成。
3. Worker 與正式 deployment baseline — 完成（process/image 邊界、pre/post deploy、restore drill template）。
4. Observability、SLO、backup/restore、runbook — 基線完成；外部 telemetry backend 仍為 P1。

### Phase 3：AI 與知識治理

1. LLM Gateway。
2. Emotion Gateway。
3. RAG version/review/publish/rollback。
4. Recommendation strategy version 與 experiment analytics。

### Phase 4：外部整合與規模化

1. POS / Payment adapters。
2. Object Storage。
3. Fleet management。
4. Analytics pipeline。
5. 經需求驗證後評估 HA 或服務拆分。

## 模組建立原則

新增模組前先回答：

- 是否有清楚的 business capability 與 owner？
- 是否已有兩個以上 callers，或現有模組責任已明顯過大？
- Contract、資料 ownership、錯誤與觀測方式是否明確？
- 能否先在 Modular Monolith 內建立 boundary，而不是立即拆服務？
- 是否有測試策略、migration/相容策略與完成條件？

沒有明確 ownership 與完成條件的想法，不新增獨立模組或新 Markdown。
