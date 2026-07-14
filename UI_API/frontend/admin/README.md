# Admin Frontend

`frontend/admin/` 是單頁營運介面，負責設定、治理、分析與維運；server-side RBAC/scoping 才是權限邊界。

`admin.js` 仍是主要 orchestrator，部分 feature 已拆成獨立模組。

## 目前頁面能力

- 狀態統計、session 結果與熱門品項。
- 系統/AI/語音/推薦功能設定。
- 推薦事件成效、活動/promotions、供應狀態。
- RAG status、documents、review、alerts、validation/rebuild。
- Member list/detail/export/delete 與 Admin audit。
- Health/dependency diagnostics、Emotion logs/settings、AI 問答測試。
- Admin login/session gate；Device/Fleet typed API 已在 backend，但目前 UI 尚非完整 fleet console。

## 入口與模組

- `admin.html`：DOM、sidebar/pages 與目前部分 inline styles。
- `admin.js`：主要 navigation、data loading、rendering 與 event orchestration。
- `features/auth/adminAuth.js`：login gate、session cookie 與 legacy header compatibility。
- `features/settings/settingsApi.js`：設定 API 邊界。
- `modules/availabilityAdmin.js`：供應狀態。
- `modules/healthAdmin.js`：維運健康。
- `modules/recommendationEventsAdmin.js`：推薦事件。
