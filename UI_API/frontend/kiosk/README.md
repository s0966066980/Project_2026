# Kiosk Frontend

`frontend/kiosk/` 是顧客自助點餐 application，目標是在 AI/provider 降級時仍能完成菜單、購物車與 checkout 主流程。

> 實作盤點：2026-07-14。`app.js` 仍是主要 orchestrator，但菜單、banner、bootstrap、cart/member/media 等責任已局部拆分。

## 目前能力

- 菜單載入、分類/filter、圖片與價格顯示。
- 購物車數量、來源追蹤、server-side repricing 與 checkout。
- 會員手機登入/註冊、常點/近期偏好推薦。
- 結構化 promotion banner、AI push、choice hesitation 推薦。
- 中英文 UI、語音串流協助、被動關鍵詞、Camera/Microphone clips。
- 互動事件、barrier inference、介入結果、WebSocket 通知。
- 付款畫面/倒數/真人協助與訂單完成；實際 Payment/POS 目前仍是 manual pilot adapter。

## 入口與模組

- `index.html`：DOM 與 Kiosk entry。
- `app.js`：runtime orchestration、screen flow、events、recommendation/voice coordination。
- `state.js`、`runtime.js`、`constants/kiosk.js`：state、runtime dependencies、labels/config。
- `cart.js`、`member.js`、`media.js`、`voice.js`：feature helpers。
- `choiceHesitation.js`、`paymentCountdown.js`：modal/flow components。
- `controllers/kioskMenuController.js`、`promoBannerController.js`：菜單與 banner controllers。
- `features/bootstrap/runtimePreferences.js`：app mode、session ID 與 local feature preferences。

## 維護規則

- Server 是價格、優惠、會員資格、供應、checkout/order/payment 結果的最終真相。
- 顧客端不顯示 raw JSON、internal score、prompt、provider/debug details。
- Camera/Microphone 必須處理拒絕、缺失、停止與 track 釋放；不可讓媒體失敗阻塞點餐。
- 事件使用穩定 name/schema，不以顯示文字作為 contract。
- Token 不長期存入 URL/`localStorage`；新 API 呼叫走 shared client。
- 不 import Admin state/auth/controller，並保持既有 DOM ids/classes。

## 驗證

```bash
cd UI_API/frontend
npm run typecheck
npm run syntax
npm run test
```

主流程變更再驗證：`開啟 Kiosk → 載入菜單 → 加入/修改購物車 → checkout → manual payment/staff flow → 完成訂單`，並視需要執行 `npm run test:e2e`。
