# POS frontend 模組說明

`frontend/pos/` 是顧客自助點餐端。

## 主要功能

- 菜單瀏覽。
- 購物車。
- 會員手機登入。
- AI 推薦顯示。
- 語音點餐。
- 結帳與付款倒數。
- 互動事件紀錄。

## 主要檔案

- `index.html`：POS 頁面。
- `app.js`：POS 主協調器。
- `cart.js`：購物車。
- `member.js`：會員流程。
- `voice.js`：語音點餐。
- `state.js`：前端狀態。
- `choiceHesitation.js`：猶豫偵測。
- `paymentCountdown.js`：付款倒數。

## 維護規則

- 顧客端只顯示必要資訊。
- 不顯示 raw JSON、內部推薦理由或模型 debug。
- 推薦卡片與語音回覆應保持簡潔。
- 不要讓固定 footer 遮住菜單內容。
