# shared frontend 模組說明

`frontend/shared/` 放置 POS 與 Admin 都可能使用的前端共用程式。

## 主要內容

- `apiClient.js`：API client。
- `httpClient.js`：HTTP helper。
- `realtimeClient.js`：WebSocket / realtime helper。
- `ui.js`：共用 UI helper。
- `styles.css`：共用樣式與目前部分 POS/Admin 樣式。

## 維護規則

- 只放真正共用的基礎工具。
- 不放 Admin 專屬業務邏輯。
- 不放 POS 專屬畫面流程。
- 後續應把 `styles.css` 拆成 base、admin、pos、components。
