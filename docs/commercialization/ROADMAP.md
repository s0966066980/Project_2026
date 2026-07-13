# 商業化 Roadmap

本 Roadmap 以可審查、可回復、保持 backward compatibility 為原則。每個 Milestone 應使用獨立 PR，達成 exit criteria 後才開始下一個大型 Milestone。

## Milestone 0：Commercial Foundation

目標：讓現況可以被持續理解、驗證與安全演進。

範圍：

- Root `AGENTS.md` 與 dependency rules。
- Current/Target architecture 文件。
- Modular Monolith、frontend boundary、AI adapter、member identity ADR。
- Risk Register 與 member migration plan。
- `.env.example`、Git ignore hygiene。
- 無 Secret、GPU、模型或外部 AI 依賴的 CI。
- Ruff、format、import validation 與漸進式 mypy。
- Frontend reproducible lockfile、typecheck 與 syntax。

Exit criteria：

- 現有 pytest 通過。
- Frontend typecheck/syntax 通過。
- Shell syntax 通過。
- CI 在 JSON storage、無 Secret、無模型環境可執行。
- 不修改 production runtime、API、UI 或 database schema。

## Milestone 1：API Contract 與 Production Packaging

目標：建立新舊 API 並存的 typed production surface。

範圍：

- `/api/v1/health`、`/api/v1/readiness`。
- `backend/schemas/api`：Checkout、Error、Health、Pagination。
- Legacy Form API compatibility adapter。
- OpenAPI contract 與 generated TypeScript client proof of concept。
- Pydantic Settings 分層與既有 `config.py` compatibility adapter。
- API/worker/static frontend Dockerfile、PostgreSQL/Redis Compose、Nginx baseline。
- Dependency profile 分離：API core、worker、AI optional。

Exit criteria：

- 舊 `/api/*` contract tests 全數保留。
- `/api/v1` schema 與 error contract tests 通過。
- API image 不含模型權重，能在 CPU/無外部 AI 下啟動並回報 readiness。
- Compose 可啟動 API/PostgreSQL/Redis。

## Milestone 2：Commercial Identity 與 Database Evolution

目標：建立 tenant/store/device/admin identity 與安全會員資料模型。

範圍：

- Tenant、Store、Device、User、Role、Permission。
- Alembic 或等價 migration orchestration。
- Member UUID、tenant scope、phone hash/encryption/mask。
- OTP/PIN authentication policy 與 audit。
- Expand/dual-write/backfill/verify/switch-read/contract。
- 所有新 business entity timestamps 使用 `TIMESTAMPTZ`。

Exit criteria：

- Tenant isolation 與 authorization integration tests。
- Device credential rotation test。
- Member backfill dry-run、resume、rollback/roll-forward 與 PII deletion tests。
- Legacy phone API 仍可透過 compatibility adapter 使用。

## Milestone 3：Frontend Toolchain 與 Feature Modules

目標：讓 Kiosk/Admin 可以獨立 build、test、deploy。

範圍：

- Vite、完整 TypeScript、Vitest、Playwright。
- Kiosk/Admin application boundary。
- Generated client 與 design-system package。
- 逐 feature 搬移，保持 DOM/route compatibility。
- Kiosk/Admin smoke test。

Exit criteria：

- Kiosk：開啟、菜單、購物車、數量、結帳、完成訂單 smoke pass。
- Admin：登入、Dashboard、活動、會員、RAG、健康狀態 smoke pass。
- 兩個 frontend artifact 可獨立部署/rollback。

React/Vue migration 不在預設範圍；若要採用，先建立獨立 ADR。

## Milestone 4：Worker、Redis 與 AI Gateways

目標：隔離長任務、共享狀態與高成本模型 failure domain。

範圍：

- Redis-backed queue、cache、rate limit、distributed lock、WebSocket fan-out。
- Worker 執行 RAG rebuild、AI inference、通知與 retry。
- LLM Gateway、Emotion Gateway、provider adapter。
- Object storage、timeout、retry、circuit breaker、dead-letter queue。

Exit criteria：

- API restart 不遺失 durable job。
- 多 API instance realtime fan-out 測試通過。
- AI provider outage 不阻斷核心 menu/checkout。
- RAG rebuild 有 idempotency、lock、progress 與 rollback。

## Milestone 5：Production Operations 與 Commerce Integration

目標：建立可觀測、可復原、可整合 POS/payment 的 production platform。

範圍：

- OpenTelemetry、metrics、tracing、SLO、alerting。
- Backup/restore automation 與定期 restore validation。
- POS adapter、payment adapter、webhook signature/idempotency。
- Order state machine、fulfillment、refund/cancel policy。
- Deployment strategy、canary、rollback、incident runbook。

Exit criteria：

- SLO 與 alert owner 明確。
- Backup restore drill 有可稽核證據。
- Payment/POS failure、duplicate、replay、out-of-order tests。
- Order write path 具 idempotency 與完整 audit trail。

## Roadmap Governance

- 每個 Milestone 一個明確 branch/PR。
- Exit criteria 未達成時，不得宣稱完成。
- Security blocker 可提前修正，但不得藉此混入下一 Milestone 的大規模搬移。
- ADR 改變時新增 superseding ADR，不覆寫歷史決策。
