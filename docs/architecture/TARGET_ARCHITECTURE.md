# 目標架構

狀態：Milestone roadmap target，不代表目前已完成

## Architecture Style

採用 **Modular Monolith First**。第一階段以清楚 domain boundary、typed contract、可替換 infrastructure adapter 與可獨立部署的執行單元為目標，不把每個 domain 拆成 microservice。

```text
Kiosk Web ───── HTTPS / WebSocket ─┐
                                   │
Admin Web ─────────── HTTPS ───────┤
                                   ▼
                        FastAPI Modular Monolith API
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
           PostgreSQL            Redis        Background Worker
                                                        │
                                      ┌─────────────────┴──────────────┐
                                      ▼                                ▼
                                 LLM Gateway                    Emotion Gateway
```

## Deployable Units

第一階段可獨立部署：

1. Kiosk Web static application。
2. Admin Web static application。
3. FastAPI API。
4. Background Worker。
5. PostgreSQL。
6. Redis。
7. LLM Gateway。
8. Emotion Gateway。

推薦、會員、菜單、活動、訂單、RAG 管理等 domain 保留在 Modular Monolith，除非日後有明確獨立 scaling、failure isolation、ownership 或 regulatory requirement。

## Long-term Repository Shape

```text
Project_2026/
├── apps/
│   ├── api/
│   ├── kiosk-web/
│   ├── admin-web/
│   └── worker/
├── packages/
│   ├── api-contracts/
│   ├── generated-client/
│   ├── design-system/
│   └── domain-types/
├── services/
│   ├── llm-gateway/
│   └── emotion-gateway/
├── migrations/
├── deploy/
├── tests/
├── docs/
└── .github/workflows/
```

此結構只能逐步建立。Milestone 0 不搬移 `UI_API/`，後續每次搬移必須保留 import/API compatibility 並提供 rollback。

## Backend Module Boundaries

```text
modules/
├── identity/
├── tenant/
├── store/
├── device/
├── catalog/
├── availability/
├── order/
├── checkout/
├── member/
├── promotion/
├── recommendation/
├── rag/
├── interaction/
├── intervention/
├── admin/
└── observability/
```

目標 module shape：

```text
module/
├── api.py
├── schemas.py
├── service.py
├── repository.py
├── models.py
├── ports.py
├── events.py
└── tests/
```

依賴規則：

- `api.py` 可依賴 schema 與 application service。
- Application service 依賴 domain model、policy 與 port。
- Infrastructure adapter 實作 repository/provider port。
- Domain 不知道 FastAPI、PostgreSQL、Redis 或模型 SDK。
- 跨 module 寫入透過明確 facade/application service；非同步工作透過 domain event/outbox 演進。

## API Strategy

- 舊 `/api/*` 與 Form API 保持可用。
- 新 API 使用 `/api/v1/*`。
- Request/response/error/pagination 以 Pydantic schema 定義。
- OpenAPI 是 contract source；TypeScript client 由 contract 產生。
- Error response 包含 stable code、human message 與 request ID。
- Write API 逐步加入 idempotency key、tenant/store/device scope 與 audit context。

## Frontend Applications

Kiosk 與 Admin 是兩個獨立 application，分別 build、test、deploy、cache 與 rollback。

允許共享：

- API contracts / generated client。
- Design tokens / reusable primitives。
- Generic HTTP/realtime utilities。
- 無 business state 的 domain types。

禁止共享：

- Business/page/DOM/authentication state。
- Feature controller。
- Kiosk session 與 Admin session implementation。

Milestone 3 才導入 Vite、完整 TypeScript、Vitest 與 Playwright。是否將 Admin 遷移至 React/Vue 必須另立 ADR。

## Commercial Identity and Scope

所有主要商業 entity 最終具備：

- `tenant_id`
- `store_id`（適用時）
- `device_id`（適用時）
- `created_at TIMESTAMPTZ`
- `updated_at TIMESTAMPTZ`

Admin authorization：User → Role → Permission → Tenant/Store scope。
Kiosk authorization：Tenant → Store → Device → Rotatable credential。

會員使用 UUID domain ID；phone 轉為加密 PII 與 lookup hash，不再作為公開或關聯主鍵。

## Data and Job Architecture

- PostgreSQL 是 durable business source of truth。
- Redis 提供 cache、distributed lock、rate limit、WebSocket fan-out 與 job coordination。
- Worker 執行 RAG rebuild、AI inference、重試、通知與長任務。
- 大型文件/媒體進 object storage；資料庫保存 metadata 與 state。
- Migration 使用 expand/migrate/contract，搭配 backup 與 restore validation。
- 重要 write/job/webhook 具 idempotency、timeout、retry 與 dead-letter strategy。

## Observability and Operations

- `/api/v1/health`：process liveness，不觸發昂貴依賴。
- `/api/v1/readiness`：PostgreSQL、Redis 與必要 adapter readiness。
- OpenTelemetry traces、structured logs、metrics、SLO 與 alert。
- PII redaction、tenant/store/device correlation、request/job ID。
- Immutable image、migration gate、canary/rolling deploy、rollback 與 restore drill。

## Milestone Guardrails

- Milestone 0：文件、CI、規範與可重現驗證。
- Milestone 1：typed API contract、settings compatibility、production packaging。
- Milestone 2：commercial identity、tenant/store/device/RBAC、Alembic、PII migration。
- Milestone 3：frontend toolchain、module migration、generated client、browser tests。
- Milestone 4：Redis/worker/gateways/object storage/resilience。
- Milestone 5：observability/SLO/payment/POS/order state/idempotency。

任何 milestone 不得藉機執行下一階段的大型搬移。
