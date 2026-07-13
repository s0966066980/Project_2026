# ADR-0001：Modular Monolith First

- 狀態：Accepted
- 日期：2026-07-13
- Owner：Core Architecture

## Context

系統已包含點餐、會員、活動、推薦、RAG、語音、情緒分析與 Admin。現況有單一 FastAPI application 與 `routes/services/repositories` 分層，但 domain boundary、資料 ownership、多租戶、部署與觀測能力仍在演進。

立即拆成大量 Microservices 會提前引入 distributed transaction、contract versioning、network failure、部署 ownership 與 observability 成本，且目前沒有足夠證據證明每個 domain 需要獨立 scaling。

## Decision

第一階段採用 Modular Monolith：

- Domain 以 module boundary、typed contract 與 dependency rule 隔離。
- 同一 API process 內透過 application service/facade 協作。
- Repository 與外部 provider 逐步使用 Port/Adapter。
- 優先獨立具有不同 runtime/scaling profile 的 Kiosk Web、Admin Web、Worker、LLM Gateway、Emotion Gateway、PostgreSQL 與 Redis。
- 不為了符合長期目錄一次搬移全部程式。

## Consequences

正面：

- 保留現有 API、WebSocket 與 UI 流程。
- 可在清楚 transaction 邊界內逐步建立 tenant/store/device model。
- 測試、部署與除錯成本低於立即 Microservices。

代價：

- 必須持續治理 dependency direction，避免退化成高耦合 monolith。
- 高成本 AI、RAG rebuild 與長時間工作需逐步移至 Worker/Gateway。
- 未來拆服務前，需要先穩定 module facade、event contract 與 data ownership。

## Alternatives

- 立即全面 Microservices：目前 domain/data/operations maturity 不足。
- Big Bang 重寫：無法合理保證 Kiosk、Admin、會員、語音與情緒流程相容。
- 永久維持純技術層分目錄：不足以支援清楚 ownership 與多租戶演進。
