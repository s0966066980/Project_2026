# UI_API Tests

`UI_API/tests/` 包含 Backend unit/route/security/architecture tests，以及需 PostgreSQL/Redis 的 integration modules。Frontend tests 位於 `UI_API/frontend/tests/`。

> 實作盤點：2026-07-14。

## 覆蓋範圍

- Identity/RBAC、Device identity、commercial scope、Member UUID/PII/session/preferences。
- Menu/availability/promotion、checkout pricing、Order/idempotency/outbox、manual Payment/POS boundary。
- Recommendation context/engine/events/feedback/experiments/governance。
- RAG document/review/alerts/governance、object storage、LLM/multimodal gateways。
- Worker claim/retry/DLQ/production handlers、analytics/fleet/control-plane durability。
- Health/observability/security/failure recovery/local profiles。
- `tests/architecture/` 檢查 route/database/module/provider boundaries 與 dead compatibility。
- PostgreSQL integration modules 驗證 migrations `0001`–`0011`、scope、identity、orders、worker；`redis_shared_integration.py` 驗證 shared adapter。
- `test_documentation_integrity.py` 檢查 first-party Markdown 相對連結。

## 執行

Target test：

```bash
cd UI_API
APP_ENV=test MEMBER_STORAGE_BACKEND=json DATABASE_URL= ENABLE_NGROK=false \
pytest -q tests/test_target.py
```

文件變更：

```bash
cd UI_API
pytest -q tests/test_documentation_integrity.py
```

Architecture：

```bash
cd UI_API
pytest -q tests/architecture
```

完整 unit/route suite 可用 `pytest -q tests`，但 PostgreSQL/Redis integration 應在對應服務與環境變數存在時個別執行。前端另從 `UI_API/frontend/` 執行 `npm run test` 或 `npm run test:e2e`。

## 測試規則

- Bug fix 優先新增可重現的 regression assertion。
- Route/API 變更測 contract、status、auth/scope 與 safe error；service 測 use case；repository 測 storage boundary。
- Migration 測版本/checksum/forward/idempotency/data result/recovery，不改寫既有 migration。
- 外部 AI/HTTP/payment/POS 使用 fake/stub/contract test；unit tests 不依賴 GPU、真實模型、外部 API 或 secrets。
- Security、checkout、PII、scope 與 worker failure 必須 fail closed 或 truthfully degraded。
- 未執行的 suite 標示 `NOT RUN`，不得描述為通過。

## 已知後續重點

- 擴大 Kiosk/Admin Playwright coverage，而非只依賴 DOM/architecture tests。
- 隨 domain cutover 把 `v1_routes.py` contract tests 對應到 module routers。
- 對 production-sized migrations、backup/restore、worker backlog 與真實 payment/POS adapters 做獨立驗證。
