# Admin Frontend

`UI_API/frontend/admin/` 是營運、設定、分析與維運介面。

## 主要能力

- 狀態統計與推薦成效。
- 系統與 AI 功能設定。
- 活動、優惠與供應狀態。
- 會員管理。
- RAG 文件、審核、告警與重建。
- 情緒分析設定與紀錄。
- 健康檢查、診斷與 AI 測試工具。

## 主要入口與模組

- `admin.html`：Admin DOM 與頁面結構；樣式應逐步移出大型 inline 區塊。
- `admin.js`：現行 orchestrator；新功能避免繼續集中。
- `modules/`：依 feature 拆分的資料載入、rendering 與事件處理。
- `features/auth/`：Admin session compatibility header、login gate 與 authenticated bootstrap。

## 維護規則

- Admin 可以顯示診斷資訊，但不得暴露不必要的 Secret、完整 PII 或原始敏感模型內容。
- 高風險操作，例如刪除、清空、匯出、發布活動、RAG rebuild，需 server-side 權限、確認與 audit。
- API 呼叫與 credential handling 集中於 client，不在各 feature 重複實作。
- 新 feature 優先建立獨立 module，不讓 `admin.js`/`admin.html` 無限制成長。
- 顯示表格與錯誤時使用安全 DOM API，不插入未驗證 HTML。
- 長期目標是 user/RBAC 與 tenant/store scope；共用 Token 只保留為相容或開發路徑。
- 不 import Kiosk business state、page state 或 feature controller。

## 最小驗證

```bash
cd UI_API/frontend
npm run typecheck
npm run syntax
```

影響主要營運流程時，另驗證 Dashboard、活動、會員、RAG 與健康頁載入。
