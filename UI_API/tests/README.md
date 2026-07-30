# UI_API Tests

`UI_API/tests/` 包含 Backend unit/route/security/architecture tests，以及需 PostgreSQL/Redis 的 integration modules。Frontend tests 位於 `UI_API/frontend/tests/`。

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
APP_ENV=test DATABASE_BACKEND=sqlite DATABASE_URL= ENABLE_NGROK=false \
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
