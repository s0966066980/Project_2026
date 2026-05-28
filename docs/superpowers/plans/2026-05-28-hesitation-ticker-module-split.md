# 猶豫卡 / AI Ticker 模組分離 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刪除舊版「還在猶豫嗎」彈跳視窗並以獨立模組重設計猶豫介入卡，同時修復 AI ticker 推播卡住／閃退問題。

**Architecture:** 把 `clearAllPushCards()` 拆成 `clearTicker()`（只清 `#recommendTicker`）和 `clearHesitationCard()`（只清 `#floatPush`）兩個獨立函式；在 `recommendation.js` closure 加入 `_currentResolve` 讓外部 `clearTicker()` 立即 resolve ticker Promise；刪除舊版 `showScenarioRecommendationCard` 並換成不碰 ticker 的輕量 `showHesitationCard()`。

**Tech Stack:** Vanilla JS (ES modules), DOM API, CSS animation

---

## File Map

| 狀態 | 路徑 | 說明 |
|------|------|------|
| Modify | `UI_API/static/recommendation.js` | 加 `_currentResolve`、拆出 `clearHesitationCard`、更新 export |
| Modify | `UI_API/static/app.js` | 刪 `showScenarioRecommendationCard`、加 `showHesitationCard`、更新 `applyIntervention`、補 `promotionPausedUntil`、移除跨層操作 |

---

## Task 1：recommendation.js — 模組分離 + Ticker Promise 修復

**Files:**
- Modify: `UI_API/static/recommendation.js:1-115`

### 背景
`clearAllPushCards()` 目前同時清 `#recommendTicker` 和 `#floatPush`。需要拆成兩個獨立函式。另外 `clearTicker()` 外部呼叫後 ticker Promise 沒有 resolve，`startRecommendLoop` 會凍結 19 秒。

- [ ] **Step 1：用完整新版覆寫 `recommendation.js`**

完整替換整個檔案：

```javascript
export function createRecommendationManager({
  ui,
  isPosActive,
  getFeatures,
  findMenuItems,
  addToCart,
  sessionPushedIds,
}) {
  let currentTicker = null;
  let dismissTimer = null;
  let _currentResolve = null;   // 修復：外部 clearTicker 時立即 resolve ticker Promise

  function clearTicker() {
    if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
    // 立即 resolve 任何待中的 ticker Promise，防止 startRecommendLoop 凍結
    const res = _currentResolve;
    _currentResolve = null;
    res?.();
    if (!ui.recommendTicker) return;
    if (currentTicker) {
      currentTicker.classList.add('ticker-fade-out');
      const t = currentTicker;
      currentTicker = null;
      setTimeout(() => { t.remove(); ui.recommendTicker?.replaceChildren(); }, 400);
    } else {
      ui.recommendTicker?.replaceChildren();
    }
  }

  function clearHesitationCard() {
    ui.floatPush?.replaceChildren();
  }

  function clearAllPushCards() {
    clearTicker();
    clearHesitationCard();
  }

  function showPushNotice(text) {
    if (!isPosActive() || !ui.floatPush) return;
    ui.floatPush.replaceChildren();
    const card = document.createElement('div');
    card.className = 'push-card push-notice';
    const p = document.createElement('p');
    p.className = 'push-notice-text';
    p.textContent = text;
    card.appendChild(p);
    ui.floatPush.appendChild(card);
    setTimeout(() => ui.floatPush?.replaceChildren(), 4000);
  }

  // 跑馬燈推薦（#recommendTicker）
  // 回傳 Promise，跑馬燈播完或關閉後 resolve。
  function showPushCard(items, reason) {
    if (!isPosActive() || !ui.recommendTicker) return Promise.resolve();
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return Promise.resolve();

    clearTicker();  // 清除前一個（同時 resolve 前一個 Promise）

    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
    const scrollText = [names, reason, priceText].filter(Boolean).join('　·　');

    const bar = document.createElement('div');
    bar.className = 'recommend-ticker-bar';

    const label = document.createElement('span');
    label.className = 'recommend-ticker-label';
    label.textContent = '⭐ 為您推薦';

    const scrollWrap = document.createElement('div');
    scrollWrap.className = 'recommend-ticker-scroll';
    const scrollEl = document.createElement('span');
    scrollEl.className = 'recommend-ticker-text';
    scrollEl.textContent = scrollText;
    scrollWrap.appendChild(scrollEl);

    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'recommend-ticker-add';
    const cartIcon = document.createElement('i');
    cartIcon.className = 'fas fa-cart-plus';
    addBtn.appendChild(cartIcon);
    addBtn.appendChild(document.createTextNode(' 加入'));

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'recommend-ticker-close';
    closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i');
    closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);

    bar.append(label, scrollWrap, addBtn, closeBtn);
    ui.recommendTicker.replaceChildren(bar);
    currentTicker = bar;

    return new Promise((resolve) => {
      _currentResolve = resolve;
      function finish() {
        if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
        _currentResolve = null;
        clearTicker();   // 視覺清理（res?.() 因 _currentResolve=null 已是 no-op）
        resolve();
      }
      addBtn.onclick = () => { itemList.forEach(item => addToCart(item)); finish(); };
      closeBtn.onclick = finish;
      scrollEl.addEventListener('animationend', finish, { once: true });
      dismissTimer = setTimeout(finish, 19500); // 保底逾時
    });
  }

  function displayRecommendation(data) {
    if (!getFeatures().recommend || !isPosActive()) return Promise.resolve();
    const ids = data.recommendation_ids || [];
    if (!ids.length) return Promise.resolve();
    const items = findMenuItems(ids);
    if (!items.length) return Promise.resolve();
    items.forEach(item => sessionPushedIds.add(item.id));
    return showPushCard(items, data.reason || '');
  }

  return { showPushCard, clearAllPushCards, clearHesitationCard, displayRecommendation, showPushNotice };
}
```

- [ ] **Step 2：語法驗證**

```bash
node --check UI_API/static/recommendation.js && echo "OK"
```

預期：`OK`

- [ ] **Step 3：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/recommendation.js
git commit -m "refactor: recommendation.js 模組分離 + ticker Promise 凍結修復

- clearTicker / clearHesitationCard / clearAllPushCards 三函式分離
- _currentResolve：clearTicker 時立即 resolve ticker Promise
- showPushCard finish() 改用 _currentResolve=null 防雙重 resolve
- export 新增 clearHesitationCard

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2：app.js — 刪除舊猶豫卡、加入新猶豫卡

**Files:**
- Modify: `UI_API/static/app.js:577-581`（更新 destructure import）
- Modify: `UI_API/static/app.js:1033-1159`（刪除 `showScenarioRecommendationCard`，換成 `showHesitationCard`）
- Modify: `UI_API/static/app.js:1182-1190`（`applyIntervention` 更新呼叫）

### 背景
`showScenarioRecommendationCard`（127 行）在開頭呼叫 `clearAllPushCards()` 殺掉 ticker，也有自己的 `resolveItems` API call 和翻書動畫。換成不碰 ticker 的輕量版。

- [ ] **Step 1：更新 destructure — 加入 `clearHesitationCard` import**

找到（`app.js` 約 577–581 行）：

```javascript
const {
  clearAllPushCards,
  displayRecommendation,
  showPushNotice
} = recommendationManager;
```

替換為：

```javascript
const {
  clearAllPushCards,
  clearHesitationCard,
  displayRecommendation,
  showPushNotice
} = recommendationManager;
```

- [ ] **Step 2：刪除 `showScenarioRecommendationCard`，插入 `showHesitationCard`**

找到（`app.js` 約 1033–1159 行）整個函式：

```javascript
async function showScenarioRecommendationCard(intervention = {}, barrierResult = {}) {
```

一直到（含）最後一行：

```javascript
  await renderWithFlip(await resolveItems());
}
```

用以下完整新函式替換：

```javascript
function showHesitationCard(intervention = {}) {
  if (!isPosActive() || !ui.floatPush) return;
  if (_isVoiceActive()) return;
  if (Date.now() - lastInteractionAt < 15000) return;
  if (Date.now() - lastValidOrderActionAt < 15000) return;

  // 只清猶豫卡區域，不碰 ticker
  clearHesitationCard();

  // 解析餐點：intervention.recommendation_ids → findMenuItems → fallback menuData 熱門
  const directIds = Array.isArray(intervention.recommendation_ids)
    ? intervention.recommendation_ids : [];
  let items = findMenuItems(directIds);
  if (!items.length) {
    items = menuData.filter(item => item && item.id && Number(item.price || 0) > 0).slice(0, 3);
  }
  items = items.slice(0, 3);
  if (!items.length) return;

  const names = items.map(i => i.name || '').filter(Boolean).join('、');

  const card = document.createElement('div');
  card.className = 'push-card';

  const header = document.createElement('div');
  header.className = 'push-card-header';
  const titleEl = document.createElement('span');
  titleEl.className = 'push-card-title';
  titleEl.textContent = '為您推薦';
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'push-close-btn';
  closeBtn.setAttribute('aria-label', '關閉');
  const closeIcon = document.createElement('i');
  closeIcon.className = 'fas fa-times';
  closeBtn.appendChild(closeIcon);
  header.append(titleEl, closeBtn);

  const nameEl = document.createElement('div');
  nameEl.className = 'push-item-names';
  nameEl.textContent = names;

  const reasonEl = document.createElement('p');
  reasonEl.className = 'push-reason';
  reasonEl.textContent = String(intervention.tts_text || '這是為您挑選的熱門餐點。');

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.className = 'push-add-btn btn-primary';
  const cartIcon = document.createElement('i');
  cartIcon.className = 'fas fa-cart-plus';
  addBtn.appendChild(cartIcon);
  addBtn.appendChild(document.createTextNode(' 加入推薦餐點'));

  card.append(header, nameEl, reasonEl, addBtn);
  ui.floatPush.replaceChildren(card);

  let timer = setTimeout(() => clearHesitationCard(), 10000);

  addBtn.addEventListener('click', () => {
    clearTimeout(timer);
    items.forEach(item => trackedAddToCart(item, { source: 'hesitation_recommendation' }));
    showPushNotice('已加入推薦餐點');
  });
  closeBtn.addEventListener('click', () => {
    clearTimeout(timer);
    clearHesitationCard();
  });
}
```

- [ ] **Step 3：更新 `applyIntervention` 呼叫點**

找到（約 1182–1190 行）：

```javascript
  if (modalName === 'recommendation_card') {
    // 只有顧客超過 15 秒沒有點選任何餐點，才顯示猶豫推播，避免干擾正在選餐的顧客
    const HESITATION_IDLE_MS = 15_000;
    if (Date.now() - lastValidOrderActionAt < HESITATION_IDLE_MS) {
      console.log('[intervention] skip recommendation_card: user acted within 15s');
      return;
    }
    showScenarioRecommendationCard(intervention, barrierResult);
    return;
  }
```

替換為：

```javascript
  if (modalName === 'recommendation_card') {
    showHesitationCard(intervention);
    return;
  }
```

（閒置條件已移入 `showHesitationCard` 本身，不需在這裡重複判斷。）

- [ ] **Step 4：語法驗證**

```bash
node --check UI_API/static/app.js && echo "OK"
```

預期：`OK`

- [ ] **Step 5：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js
git commit -m "refactor: 刪除 showScenarioRecommendationCard，換成 showHesitationCard

- 刪除舊版猶豫卡（127行：翻書動畫、resolveItems API call）
- 新增 showHesitationCard：只用 clearHesitationCard()，不碰 ticker
- applyIntervention recommendation_card 分支改呼叫 showHesitationCard

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3：app.js — `startRecommendLoop` 補 `promotionPausedUntil` + 移除跨層操作

**Files:**
- Modify: `UI_API/static/app.js:1574-1593`（`fetchAndDisplayRecommend`）
- Modify: `UI_API/static/app.js:1595-1608`（`startRecommendLoop`）

### 背景
1. `startRecommendLoop` 目前完全不檢查 `promotionPausedUntil`，checkout 後的 45 秒推播暫停無效。
2. `fetchAndDisplayRecommend` 有一行 `clearTimeout(interactionModalTimer)` — 推播函式不應管介入計時器（錯誤的跨層操作）。

- [ ] **Step 1：修改 `fetchAndDisplayRecommend` — 移除跨層操作**

找到（約 1574–1593 行）：

```javascript
async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (_isVoiceActive()) return;
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return;
  if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
  const fd = new FormData();
  fd.append('session_id', sessionId);
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 12000);
  try {
    const data = await api.autoRecommend(fd, ctrl.signal);
    if (data.status === 'success') return displayRecommendation(data); // intentionally not awaited — caller (startRecommendLoop) awaits the returned ticker Promise
  } catch (err) {
    console.warn('[auto_recommend failed]', err);
  } finally {
    clearTimeout(tid);
  }
}
```

替換為（移除 `interactionModalTimer` 那行）：

```javascript
async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (_isVoiceActive()) return;
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return;
  const fd = new FormData();
  fd.append('session_id', sessionId);
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 12000);
  try {
    const data = await api.autoRecommend(fd, ctrl.signal);
    if (data.status === 'success') return displayRecommendation(data); // intentionally not awaited — caller (startRecommendLoop) awaits the returned ticker Promise
  } catch (err) {
    console.warn('[auto_recommend failed]', err);
  } finally {
    clearTimeout(tid);
  }
}
```

- [ ] **Step 2：修改 `startRecommendLoop` — 補 `promotionPausedUntil` 檢查**

找到（約 1595–1608 行）：

```javascript
async function startRecommendLoop() {
  if (isAdminMode() || recommendLoopActive) return;
  recommendLoopActive = true;
  while (recommendLoopActive) {
    if (!isPosActive() || document.hidden) {
      await new Promise(r => setTimeout(r, 1000));
      continue;
    }
    // tickerDone is the ticker Promise returned (not awaited) by fetchAndDisplayRecommend
    const tickerDone = await fetchAndDisplayRecommend();
    if (tickerDone && recommendLoopActive) await tickerDone;
    if (recommendLoopActive) await new Promise(r => setTimeout(r, 10_000));
  }
}
```

替換為：

```javascript
async function startRecommendLoop() {
  if (isAdminMode() || recommendLoopActive) return;
  recommendLoopActive = true;
  while (recommendLoopActive) {
    if (!isPosActive() || document.hidden || Date.now() < promotionPausedUntil) {
      await new Promise(r => setTimeout(r, 1000));
      continue;
    }
    // tickerDone is the ticker Promise returned (not awaited) by fetchAndDisplayRecommend
    const tickerDone = await fetchAndDisplayRecommend();
    if (tickerDone && recommendLoopActive) await tickerDone;
    if (recommendLoopActive) await new Promise(r => setTimeout(r, 10_000));
  }
}
```

- [ ] **Step 3：語法驗證**

```bash
node --check UI_API/static/app.js && echo "OK"
```

預期：`OK`

- [ ] **Step 4：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js
git commit -m "fix: startRecommendLoop 補 promotionPausedUntil 檢查，移除跨層計時器操作

- startRecommendLoop: 補 Date.now() < promotionPausedUntil 條件
  checkout 後的推播暫停現在實際有效
- fetchAndDisplayRecommend: 移除 clearTimeout(interactionModalTimer)
  推播函式不應管介入計時器

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4：全域驗證

**Files:** 無修改，只做驗證。

- [ ] **Step 1：JS 語法全檢**

```bash
cd /home/oliver/Project_2026
node --check UI_API/static/recommendation.js && echo "recommendation.js OK"
node --check UI_API/static/app.js && echo "app.js OK"
```

預期：兩行都印出 `OK`。

- [ ] **Step 2：確認 showScenarioRecommendationCard 已完全刪除**

```bash
grep -n "showScenarioRecommendationCard\|renderWithFlip\|resolveItems\|_clearScenarioTimer\|push-card-flip" UI_API/static/app.js
```

預期：**無任何輸出**（0 行）。

- [ ] **Step 3：確認新猶豫卡只碰 floatPush，不碰 ticker**

```bash
grep -n "clearTicker\|recommendTicker\|clearAllPushCards" UI_API/static/app.js | grep -A2 -B2 "showHesitationCard"
```

預期：`showHesitationCard` 函式本體內**不出現** `clearTicker`、`recommendTicker`、`clearAllPushCards`。

用以下更直接的方式確認：

```bash
awk '/^function showHesitationCard/,/^\}/' UI_API/static/app.js | grep -E "clearTicker|recommendTicker|clearAllPushCards"
```

預期：**無任何輸出**（函式內沒有碰 ticker）。

- [ ] **Step 4：確認 _currentResolve 正確串接**

```bash
grep -n "_currentResolve\|res?.()" UI_API/static/recommendation.js
```

預期：至少出現 3 行（宣告、clearTicker 裡的呼叫、showPushCard 裡的賦值）。

- [ ] **Step 5：確認 promotionPausedUntil 補進 startRecommendLoop**

```bash
grep -n "promotionPausedUntil" UI_API/static/app.js
```

預期：輸出中有一行位於 `startRecommendLoop` 函式內（行號約在 1598–1605 範圍）。

---

## Self-Review

**Spec coverage:**
- ✅ 刪除「還在猶豫嗎」彈窗 → Task 2 Step 2
- ✅ 模組分離（clearHesitationCard vs clearTicker）→ Task 1 Step 1
- ✅ 新猶豫卡不碰 ticker → Task 2 Step 2（`clearHesitationCard()` only）
- ✅ Ticker Promise 凍結修復 → Task 1 Step 1（`_currentResolve`）
- ✅ `promotionPausedUntil` 補進 startRecommendLoop → Task 3 Step 2
- ✅ 移除跨層 `interactionModalTimer` 操作 → Task 3 Step 1

**Placeholder scan:** 無 TBD/TODO，所有程式碼完整。

**Type consistency:**
- `clearHesitationCard` — Task 1 export、Task 2 Step 1 destructure、Task 2 Step 2 函式內使用 ✅
- `_currentResolve` — Task 1 宣告、`clearTicker` 呼叫、`showPushCard` 賦值 ✅
- `showHesitationCard` — Task 2 Step 2 定義、Task 2 Step 3 呼叫 ✅
