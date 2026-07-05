# tests 模組說明

`tests/` 放置 UI_API 後端測試。

## 覆蓋範圍

- 會員服務與會員 routes。
- 推薦上下文、推薦引擎、推薦事件與回饋。
- RAG 文件、審核、offer guard 與告警。
- 活動與供應狀態。
- PostgreSQL migration。
- 健康檢查與 observability。
- 安全邊界與 feature flags。

## 執行方式

```bash
cd UI_API
MEMBER_STORAGE_BACKEND=json DATABASE_URL= pytest -q tests
```

## 維護規則

- 新 service 應補 service test。
- 新 route 應補 route 或 integration test。
- 新 repository 應補資料讀寫測試。
- 修 bug 時應優先新增能重現問題的測試。
