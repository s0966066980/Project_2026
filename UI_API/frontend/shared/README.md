# Shared Frontend

`frontend/shared/` 只保存 Kiosk 與 Admin 可共同使用的 transport、contracts、hooks 與 UI primitives。

## 目前內容

- `apiClient.js`：legacy `/api/*` facade、Kiosk/Admin compatibility headers、token URL cleanup、voice streaming/checkout helpers。
- `httpClient.js`：JSON/form HTTP helpers。
- `realtimeClient.js`：WebSocket connect/reconnect 與訊息處理。
- `api/v1Client.ts`：typed `/api/v1` client，提供 same-origin credentials、request ID、timeout、GET retry 與 safe errors。
- `contracts/api-v1.ts`：v1 response/error/DTO transport types。
- `components/VisibilityDisplay.js`、`hooks/useDomEvents.js`：共用 DOM primitives。
- `ui.js`、`styles.css`：共用 UI references/helpers 與目前跨 Kiosk/Admin 樣式。

## 邊界

- 不放 Admin/Kiosk 專屬 business、page、auth 或 controller state。
- 新 API 呼叫優先透過 client；legacy → v1 採 endpoint-by-endpoint 漸進切換。
- HTTP retry 只用於安全/idempotent 操作；write 必須尊重 server idempotency contract。
- 不在 browser 重做價格、promotion、permission、member scope 或 order state policy。
- 未驗證資料不直接進 `innerHTML`；credential 不放 URL 或 `localStorage`。
- `styles.css` 仍混有兩端樣式；只有在建立相容 migration/test 時才拆分，避免破壞既有 selectors。
