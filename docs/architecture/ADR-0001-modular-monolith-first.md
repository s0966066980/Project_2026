# ADR-0001：Modular Monolith First

- 狀態：Accepted
- 日期：2026-07-13

## Context

系統同時包含點餐、會員、活動、推薦、RAG、互動、語音、情緒分析與 Admin。現況已有單一 FastAPI application 與 routes/services/repositories 分層，但 domain boundary 尚未成熟，資料仍有 JSON/PostgreSQL 雙路徑，部署與觀測能力也未完成。

若現在直接拆成大量 microservices，會先產生分散式 transaction、contract version、network failure、deployment ownership 與 observability 成本，卻沒有足夠證據證明每個 domain 需要獨立 scaling。

## Decision

第一階段採用 Modular Monolith：

- Domain 以 module boundary、typed contract 與 dependency rule 隔離。
- 同一 API process 內使用明確 application service/facade 協作。
- Repository 與外部 provider 以 Port/Adapter 演進。
- 只有具有不同 runtime/scaling profile 的 Kiosk Web、Admin Web、Worker、LLM Gateway、Emotion Gateway、PostgreSQL、Redis 成為獨立執行單元。

## Consequences

正面：

- 保留現有 API 與流程，避免 Big Bang Rewrite。
- 可以在單一 transaction 邊界內逐步建立 tenant/store/order model。
- 測試與部署複雜度低於立即 microservices。

代價：

- 必須主動治理 module dependency，否則會退化成 distributed-looking monolith。
- 高成本 AI task 仍需及早移到 worker/gateway，避免拖累 API。
- 未來拆分服務時需要穩定 module facade 與 event contract。

## Rejected Alternatives

- 立即全面 Microservices：domain/data/operations maturity 不足。
- Big Bang 重寫：無法保證 Kiosk、Admin、語音與情緒流程相容。
- 永久維持目前依檔案分層：不足以支援 tenant/store/device scope 與清楚 ownership。
