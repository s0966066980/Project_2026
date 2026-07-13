# UI_API Tests

`UI_API/tests/` 保存 Backend 的 unit、route、repository、migration 與整合邊界測試。

## 目前覆蓋

- 會員、Session、偏好與訂單。
- 推薦上下文、推薦引擎、推薦事件與回饋。
- 活動、優惠、Checkout pricing 與供應狀態。
- RAG 文件、審核、offer guard 與告警。
- PostgreSQL repository/migration。
- PostgreSQL migration foundation unit tests；integration suite 由 CI 的 disposable PostgreSQL 顯式執行。
- 健康檢查、observability、feature flag 與安全邊界。

## 執行

完整 Backend tests：

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

開發時優先跑目標測試：

```bash
cd UI_API
pytest -q tests/<target_test_file>.py
```

若修改共享 contract、authentication、checkout、會員資料或 repository，再擴大至完整測試。

## 測試規則

- Bug fix 優先新增可重現失敗的 regression test。
- Route 變更新增 route/contract test。
- Service 變更新增 service/use-case test。
- Repository 變更同時驗證 JSON/PostgreSQL boundary（適用時）。
- Migration 變更驗證版本、checksum、forward、資料結果與 recovery。
- 外部 AI/HTTP 使用 fake、stub 或 mock；CI 不依賴 GPU、真實模型、外部 API 或 Secret。
- 測試不得依賴執行順序、真實會員資料或未清理的本機 runtime 檔案。
- 未執行的測試標示 `NOT RUN`，不得宣稱通過。

## 後續

優先補：

- Kiosk Playwright smoke。
- Admin Playwright smoke。
- API v1 contract tests。
- Checkout、promotion 與 recommendation 的跨層回歸。
- PostgreSQL backup/restore 定期演練與 production-sized migration 壓力測試。

優先級見 [`docs/FUTURE_MODULES.md`](../../docs/FUTURE_MODULES.md)。
