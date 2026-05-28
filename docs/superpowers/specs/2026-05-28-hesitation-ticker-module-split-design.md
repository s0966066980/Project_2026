# 猶豫卡 / AI Ticker 模組分離設計

**Goal:** 刪除舊版「還在猶豫嗎」彈跳視窗，以獨立模組重設計猶豫介入卡，並修復 AI ticker 推播卡住／閃退問題。

---

## 背景與問題根源

### DOM 區域
- `#recommendTicker` — AI ticker 跑馬燈專用
- `#floatPush` — 猶豫卡、通知 toast 共用

兩個 DOM 元素本來就分開，但有三個互相污染點：

1. **`clearAllPushCards()` 同時清兩個區域** — `showScenarioRecommendationCard` 在開頭呼叫它，直接殺掉正在跑的 ticker。
2. **Ticker Promise 凍結** — 外部呼叫 `clearTicker()` 移除 DOM 後，`animationend` 永不觸發，`startRecommendLoop` 等到 19500ms 保底逾時才繼續（凍結 ~19s）。
3. **跨層操作** — `fetchAndDisplayRecommend` 裡有 `clearTimeout(interactionModalTimer)`，推播函式不應管介入計時器。
4. **`promotionPausedUntil` 未被 `startRecommendLoop` 檢查** — checkout 後的推播暫停完全無效。

---

## 設計

### 1. 模組分離（`recommendation.js`）

拆出三個清除函式，各自只負責自己的 DOM 區域：

| 函式 | 清除對象 | 使用場景 |
|------|----------|----------|
| `clearTicker()` | `#recommendTicker` only | ticker 內部 + 外部強制中斷 |
| `clearHesitationCard()` | `#floatPush` only | 猶豫卡內部 |
| `clearAllPushCards()` | 兩者 | session reset、語音開始、功能關閉 |

`clearHesitationCard` 加入 export 供 `app.js` 使用。

`clearAllPushCards` 保持為 `clearTicker() + clearHesitationCard()` 組合，現有呼叫點（session reset、語音開始、feature 關閉）不變。

### 2. Ticker Promise 凍結修法（`recommendation.js`）

在 closure 加入 `_currentResolve`：

```javascript
let _currentResolve = null;

function clearTicker() {
  if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
  const res = _currentResolve;
  _currentResolve = null;
  res?.();          // 立即 resolve，startRecommendLoop 不再卡
  // 再做 fade-out 視覺動畫（不影響 Promise）
  if (currentTicker) {
    currentTicker.classList.add('ticker-fade-out');
    const t = currentTicker; currentTicker = null;
    setTimeout(() => { t.remove(); ui.recommendTicker?.replaceChildren(); }, 400);
  } else {
    ui.recommendTicker?.replaceChildren();
  }
}

function showPushCard(items, reason) {
  // ...
  clearTicker(); // clears previous + resolves previous promise
  // build DOM ...
  return new Promise((resolve) => {
    _currentResolve = resolve;
    function finish() {
      if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
      _currentResolve = null;
      clearTicker();   // visual cleanup (res?.() is no-op since _currentResolve = null)
      resolve();
    }
    addBtn.onclick = () => { itemList.forEach(item => addToCart(item)); finish(); };
    closeBtn.onclick = finish;
    scrollEl.addEventListener('animationend', finish, { once: true });
    dismissTimer = setTimeout(finish, 19500);
  });
}
```

不論觸發方式（animationend、按鈕、外部 clearTicker），Promise 一律立即 resolve。

### 3. 新猶豫卡 `showHesitationCard(intervention)`（`app.js`）

**刪除**：`showScenarioRecommendationCard`（約 130 行，含翻書動畫、`resolveItems` API call、`renderWithFlip`）

**新增**：`showHesitationCard(intervention)` — 約 40 行

行為規格：
- 進入條件：`isPosActive()` && `!_isVoiceActive()` && 距 `lastInteractionAt` ≥ 15s && 距 `lastValidOrderActionAt` ≥ 15s
- 餐點來源：`intervention.recommendation_ids` → `findMenuItems()` 找；若空，fallback 到 `menuData` 中價格 > 0 的前 3 項
- 清除動作：只呼叫 `clearHesitationCard()`，**不呼叫 `clearTicker()` 或 `clearAllPushCards()`**
- DOM 寫入：`ui.floatPush.replaceChildren(card)` 
- 自動關閉：`setTimeout(clearHesitationCard, 10000)` 局部計時器
- 按鈕：「加入推薦餐點」（trackedAddToCart + showPushNotice） + 「✕ 關閉」
- **無**「換一個推薦」按鈕（避免額外 API call）
- **無** flip 動畫

`applyIntervention` 中 `recommendation_card` 分支：

```javascript
if (modalName === 'recommendation_card') {
  const HESITATION_IDLE_MS = 15_000;
  if (Date.now() - lastValidOrderActionAt < HESITATION_IDLE_MS) return;
  showHesitationCard(intervention);
  return;
}
```

### 4. 其他修補（`app.js`）

**`startRecommendLoop` 補 `promotionPausedUntil` 檢查：**

```javascript
while (recommendLoopActive) {
  if (!isPosActive() || document.hidden || Date.now() < promotionPausedUntil) {
    await new Promise(r => setTimeout(r, 1000));
    continue;
  }
  const tickerDone = await fetchAndDisplayRecommend();
  if (tickerDone && recommendLoopActive) await tickerDone;
  if (recommendLoopActive) await new Promise(r => setTimeout(r, 10_000));
}
```

**`fetchAndDisplayRecommend` 移除跨層操作：**

刪除這行（推播函式不應管介入計時器）：
```javascript
if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
```

---

## 修改範圍

| 檔案 | 動作 |
|------|------|
| `UI_API/static/recommendation.js` | 加 `_currentResolve`、拆出 `clearHesitationCard`、更新 export |
| `UI_API/static/app.js` | 刪 `showScenarioRecommendationCard`、加 `showHesitationCard`、更新 `applyIntervention`、補 `promotionPausedUntil`、移除跨層操作 |

HTML / CSS 不需改動（`#floatPush`、`.push-card` 樣式沿用）。

---

## 不在範圍內

- 不改 `clearAllPushCards()` 的現有呼叫點（session reset 等情境仍清兩者是正確行為）
- 不改 `applyIntervention disable_promotion` 邏輯（呼叫 `clearAllPushCards()` 是正確的，修完後 Promise 會立即 resolve 不再卡）
- 不改其他 barrier_state 的介入邏輯
