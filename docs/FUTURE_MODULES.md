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
| P1 | Order outbox consumption | 可靠發布 Order lifecycle event | 1G transactional outbox、Worker | retry、backoff、dead letter、replay、backlog metrics |
| P0 | Commercial observability | 建立正式營運監控 | Deployment | metrics、trace、alert、SLO、runbook |
| P1 | API v1 contracts | 建立 typed、versioned API | Pydantic/OpenAPI | `/api/v1`、統一 error、相容層 |
| P1 | Frontend toolchain | 提升 Kiosk/Admin 可維護性 | API contracts | Vite、TypeScript、Vitest、Playwright |
| P1 | Frontend feature modules | 拆分大型協調器與樣式 | Frontend toolchain | Kiosk/Admin boundary 清楚且回歸測試通過 |
| P1 | Redis shared infrastructure | 支援多 instance | Deployment | shared rate limit、cache、lock/queue |
| P1 | Worker | 移出長時間與可重試工作 | Redis | RAG rebuild、報表、事件與 AI job 可觀測 |
| P1 | LLM Gateway | 標準化文字生成 Provider | Port/Adapter | timeout、retry、fallback、metrics |
| P1 | Emotion Gateway | 隔離 GPU 模型 runtime | Port/Adapter | 統一 contract、健康檢查、fallback |
| P1 | RAG governance | 文件版本、審核、發布與 rollback | Worker、Object storage | 可追蹤版本與 rebuild 結果 |
| P1 | Promotion / Recommendation governance | 策略版本與成效治理 | Event data | exposure、click、conversion、experiment 分析 |
| P2 | Object Storage | 管理文件、音訊、影片與匯出物 | Security/Privacy | lifecycle、encryption、signed access |
| P2 | POS / Payment adapters | 串接正式交易系統 | Order state machine | provider contract、reconciliation、failure handling |
| P2 | Fleet management | 管理大量 Kiosk | Device identity | heartbeat、版本、遠端設定、分批發布 |
| P2 | Data analytics pipeline | 建立營運與推薦分析 | Event contract | 可重播、資料品質與 dashboard |
| P2 | Multi-region / HA | 提升大規模可用性 | SLO、observability | 經容量與故障資料證明需求 |

## 建議執行順序

### Phase 1：商用資料與權限基礎

1. 完成 Tenant / Store / Device enforcement（foundation 已建立）。
2. Member UUID / PII。
3. Order / Checkout hardening。

### Phase 2：工程化與營運

1. API v1 contracts。
2. Frontend toolchain 與 feature modules。
3. Redis、Worker 與正式 deployment baseline。
4. Observability、SLO、backup/restore、runbook。

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
