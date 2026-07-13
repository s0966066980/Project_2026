# Kiosk Frontend

`UI_API/frontend/kiosk/` 是顧客自助點餐 application，目標是穩定、清楚、低干擾地完成點餐。

## 主要能力

- 菜單瀏覽、分類與品項顯示。
- 購物車、數量、價格與來源追蹤。
- 會員手機登入與常點推薦。
- 結構化活動與 AI 推薦。
- 語音點餐、被動協助與多語系。
- 互動事件、猶豫/困惑介入與情緒流程。
- Checkout、付款倒數與訂單完成。

## 主要入口與模組

- `index.html`：Kiosk DOM 與頁面入口。
- `app.js`：現行 application orchestrator；新功能避免繼續無限制集中。
- `state.js`：Kiosk runtime state。
- `cart.js`：購物車。
- `member.js`：會員流程。
- `media.js`：Camera/Microphone 與事件片段。
- `choiceHesitation.js`：選擇猶豫流程。
- `paymentCountdown.js`：付款倒數。
- `controllers/`：菜單、活動等 feature controller。

## 維護規則

- 顧客端只顯示完成任務所需資訊，不顯示 raw JSON、內部 score、Prompt 或模型 debug。
- Server 是價格、優惠、會員資格與 Checkout 結果的最終真相。
- 固定 Topbar、推薦區與 Bottom navigation 不得遮住菜單或主要操作。
- Camera/Microphone 需明確處理權限拒絕、裝置缺失與停止釋放。
- 互動事件需使用穩定 event name/schema，避免以顯示文字作為資料 contract。
- 新功能優先放入 feature controller/service，不讓 `app.js` 持續成長。
- 不 import Admin business state 或 authentication。

## 最小驗證

```bash
cd UI_API/frontend
npm run typecheck
npm run syntax
```

影響點餐主流程時，另驗證：

```text
開啟 Kiosk → 載入菜單 → 加入/修改購物車 → 進入結帳 → 完成訂單
```
