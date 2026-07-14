# Admin Frontend

`frontend/admin/` 是單頁營運介面，負責設定、治理、分析與維運；server-side RBAC/scoping 才是權限邊界。

> 實作盤點：2026-07-14。`admin.js` 仍是大型 orchestrator，只有部分 feature 已拆模組。

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

## 已知技術債

- `admin.js`/`admin.html` 體積大，RAG、promotion、member、stats、emotion/test 等能力尚未各自拆 module。
- Admin 多數呼叫仍是 legacy `/api/*` raw `fetch()`；typed `shared/api/v1Client.ts` 尚未全面導入。
- 部分 rendering 仍使用經 `escHtml()` 處理的 `innerHTML`；新 code 優先建立 DOM node/`textContent`。

## 維護與驗證

- 高風險操作需 server permission、明確確認與 audit；UI 隱藏按鈕不等於授權。
- 不顯示 secret、raw token、完整 PII、未遮罩模型內容或 provider error。
- 新 feature 優先放獨立 module，並透過 shared client；不 import Kiosk state/controller。
- 保持現有 DOM ids/classes 與 sidebar page contracts。

```bash
cd UI_API/frontend
npm run typecheck
npm run syntax
npm run test
```

影響 Admin critical flow 時再執行 `npm run test:e2e`。
