# AI推播 UX 升級實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復並升級 AI推播系統：閒置 15 秒才彈跳視窗、放大 popup、換一個用翻書特效、跑馬燈播完後再等 10 秒循環、多樣化餐點推薦風格。

**Architecture:** 後端 `recommendation_service.py` 新增四種推薦風格輪流切換，前端分三層改動：CSS（大小 + 動畫）、`recommendation.js`（跑馬燈單次播放 + Promise 回傳）、`app.js`（閒置門檻 + 翻書特效 + async 循環）。

**Tech Stack:** Python / FastAPI（後端 style 注入）、Vanilla JS ES2022（async/await loop）、CSS 3D transform（翻書）、CSS `animationend` event（計時）。

---

## 檔案一覽

| 動作 | 路徑 | 職責 |
|------|------|------|
| 修改 | `UI_API/services/recommendation_service.py` | 加四種風格輪流 + prompt suffix |
| 修改 | `UI_API/routes/recommendation_routes.py` | 把 `recommendation_style` / `recommendation_label` 透傳 |
| 修改 | `UI_API/static/styles.css` | floatPush 放大 + flip 動畫 + ticker 單次 + label 顏色 |
| 修改 | `UI_API/static/recommendation.js` | showPushCard 回傳 Promise + style label + 單次動畫 |
| 修改 | `UI_API/static/app.js` | 閒置偵測 + 翻書換頁 + async 推播循環 |

---

## Task 1：後端 — 推薦風格輪播

**Files:**
- Modify: `UI_API/services/recommendation_service.py:1-10, 407-440`

- [ ] **Step 1：在模組頂部加 `itertools` import 與四種風格定義**

在 `recommendation_service.py` 第 1 行 `import asyncio` 後面新增：

```python
import itertools

_RECOMMENDATION_STYLES = itertools.cycle([
    {
        "key": "popular",
        "label": "⭐ 人氣組合",
        "prompt_suffix": "推薦點擊率最高、最多顧客喜愛的搭配，口味大眾化，主餐＋飲料各一。",
    },
    {
        "key": "diet",
        "label": "🥗 減脂選擇",
        "prompt_suffix": "推薦低卡、低脂或含蔬菜的選項，適合注重健康的顧客；飲料優先選零卡或無糖。",
    },
    {
        "key": "evil_combo",
        "label": "😈 邪惡組合",
        "prompt_suffix": "推薦高熱量、超滿足的邪惡組合，強調美味與份量，讓顧客盡情享受，可含雙層牛肉或大薯。",
    },
    {
        "key": "value",
        "label": "💰 超值套餐",
        "prompt_suffix": "推薦性價比最高的搭配，讓顧客用最少的錢吃到最多份量，優先推超值全餐系列。",
    },
])
```

- [ ] **Step 2：修改 `generate_recommendation`，用 `next(_RECOMMENDATION_STYLES)` 取當次風格**

把 `generate_recommendation` 函式的 `user_prompt` 建構與 `return` 改成：

```python
async def generate_recommendation(session_id: str, ollama_semaphore) -> dict:  # noqa: ARG001
    """Ollama 推播：根據完整菜單與 RAG 推薦餐點，每次輪換推薦風格。"""
    style = next(_RECOMMENDATION_STYLES)
    full_menu_context, rag_context = await asyncio.gather(
        asyncio.to_thread(database.build_full_menu_context),
        asyncio.to_thread(database.retrieve_menu_from_rag, "推薦餐點"),
    )
    user_prompt = (
        f"{full_menu_context}\n\n"
        f"【RAG 補充規則與知識】\n{rag_context or '（無補充）'}\n\n"
        f"【本次推薦風格】{style['prompt_suffix']}\n\n"
        "推薦規則：\n"
        "1. recommendation_ids 只能使用【完整菜單白名單】中存在的 ID。\n"
        "2. reason 最多 40 字，語氣像店員輕聲提醒，必須提到真實菜單品項名稱。\n"
        "推薦 1~3 個餐點。"
    )
    system_prompt = config.get("RECOMMEND_SYSTEM_PROMPT")
    menu_items = await asyncio.to_thread(menu_repository.get_menu)
    menu_ids = [item.get("id") for item in menu_items if item.get("id")]
    loop = asyncio.get_running_loop()
    async with ollama_semaphore:
        raw = await loop.run_in_executor(None, ai_services.ask_ollama, system_prompt, user_prompt)
    if isinstance(raw, list):
        raw = next((r for r in raw if isinstance(r, dict)), {})
    elif not isinstance(raw, dict):
        raw = {}
    if "error" in raw:
        return {"status": "error", "message": raw["error"], "raw_content": raw.get("raw_content", "")}
    rec = coerce_recommendation(raw, menu_ids, menu_items=menu_items)
    return {
        "status": "success",
        "mode": "ai",
        "recommendation_ids": rec["recommendation_ids"],
        "reason": rec["reason"],
        "ollama_result": rec["ollama_result"],
        "recommendation_style": style["key"],
        "recommendation_label": style["label"],
    }
```

- [ ] **Step 3：`get_default_recommendation` 也加 style 欄位（fallback 用 popular）**

找到 `get_default_recommendation` 的 `return` 區塊，改成：

```python
    return {
        "status": "success",
        "mode": "default",
        "recommendation_ids": ids,
        "reason": reason,
        "ollama_result": "",
        "recommendation_style": "popular",
        "recommendation_label": "⭐ 人氣組合",
    }
```

- [ ] **Step 4：語法檢查**

```bash
python3 -m py_compile UI_API/services/recommendation_service.py
echo "OK"
```

預期輸出：`OK`（無錯誤）

- [ ] **Step 5：Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/services/recommendation_service.py
git commit -m "feat: recommendation 四種風格輪播 (popular/diet/evil_combo/value)"
```

---

## Task 2：後端 — 路由透傳 style 欄位

**Files:**
- Modify: `UI_API/routes/recommendation_routes.py`

- [ ] **Step 1：確認 route 直接回傳 service 的 response dict**

目前 `recommendation_routes.py` 第 25 行 `return response` 已直接回傳 service 的 dict，`recommendation_style` / `recommendation_label` 自然被帶出。Fallback 路徑也已從 `get_default_recommendation` 取得。**無需修改 route 檔案。**

驗證：

```bash
python3 -m py_compile UI_API/routes/recommendation_routes.py
echo "OK"
```

---

## Task 3：CSS — Popup 放大 + 翻書動畫 + Ticker 單次 + Label 顏色

**Files:**
- Modify: `UI_API/static/styles.css` (行約 1942–2101)

- [ ] **Step 1：放大 `#floatPush` 容器**

找到：
```css
#floatPush {
  position: fixed;
  bottom: 110px;   /* 高於底部列 + 間距 */
  left: 50%;
  transform: translateX(-50%);
  z-index: 980;
  width: clamp(260px, 88vw, 360px);
  pointer-events: none;
}
```

改成：
```css
#floatPush {
  position: fixed;
  bottom: 110px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 980;
  width: clamp(340px, 92vw, 520px);
  pointer-events: none;
  perspective: 900px;   /* 翻書特效景深 */
}
```

- [ ] **Step 2：放大 `.push-card` 本體樣式**

找到：
```css
.push-card {
  pointer-events: all;
  background: rgba(20, 20, 20, 0.82);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  color: #fff;
  border-radius: 16px;
  padding: 14px 16px 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.38);
  animation: push-slide-up 0.3s ease-out forwards;
}
```

改成：
```css
.push-card {
  pointer-events: all;
  background: rgba(20, 20, 20, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  color: #fff;
  border-radius: 18px;
  padding: 18px 20px 18px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.42);
  animation: push-slide-up 0.3s ease-out forwards;
  transform-origin: center;
  backface-visibility: hidden;
}
```

- [ ] **Step 3：放大卡片內品名字體**

找到：
```css
.push-item-names {
  font-size: 17px; font-weight: 800; line-height: 1.3; color: #fff; margin-bottom: 4px;
}
```

改成：
```css
.push-item-names {
  font-size: 20px; font-weight: 800; line-height: 1.3; color: #fff; margin-bottom: 6px;
}
```

- [ ] **Step 4：新增翻書動畫 keyframes（在 `push-fade-out` keyframes 後面插入）**

找到：
```css
@keyframes push-fade-out {
  to { opacity: 0; transform: translateY(10px); }
}
```

在其後新增：
```css
@keyframes push-flip-out {
  from { transform: rotateY(0deg); opacity: 1; }
  to   { transform: rotateY(90deg); opacity: 0; }
}
@keyframes push-flip-in {
  from { transform: rotateY(-90deg); opacity: 0; }
  to   { transform: rotateY(0deg); opacity: 1; }
}
.push-card-flip-out {
  animation: push-flip-out 0.22s ease-in forwards !important;
}
.push-card-flip-in {
  animation: push-flip-in 0.22s ease-out forwards !important;
}
```

- [ ] **Step 5：Ticker 動畫改為單次播放**

找到：
```css
.recommend-ticker-text {
  white-space: nowrap;
  position: absolute;
  top: 0;
  left: 0;
  line-height: 22px;
  font-size: 14px;
  font-weight: 600;
  /* 從右側進入，往左滾出 */
  padding-left: 100%;
  animation: ticker-scroll 16s linear infinite;
}
```

改成：
```css
.recommend-ticker-text {
  white-space: nowrap;
  position: absolute;
  top: 0;
  left: 0;
  line-height: 22px;
  font-size: 14px;
  font-weight: 600;
  padding-left: 100%;
  animation: ticker-scroll 18s linear 1 forwards;
}
```

- [ ] **Step 6：Ticker label 依風格變色（在 `.recommend-ticker-label` 後面新增）**

找到：
```css
.recommend-ticker-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  white-space: nowrap;
  padding: 3px 9px;
  background: rgba(255,255,255,0.18);
  border-radius: 6px;
}
```

在其後插入：
```css
.recommend-ticker-label[data-style="diet"]       { background: rgba(76,175,80,0.32); }
.recommend-ticker-label[data-style="evil_combo"] { background: rgba(156,39,176,0.32); }
.recommend-ticker-label[data-style="value"]      { background: rgba(255,193,7,0.28); }
```

- [ ] **Step 7：JS 語法檢查（CSS 本身不需編譯，確認節點在瀏覽器可解析）**

```bash
node --check UI_API/static/app.js
node --check UI_API/static/recommendation.js
echo "syntax OK"
```

- [ ] **Step 8：Commit**

```bash
git add UI_API/static/styles.css
git commit -m "style: floatPush 放大、翻書動畫、ticker 單次、label 風格色"
```

---

## Task 4：JS recommendation.js — showPushCard 回傳 Promise + style label

**Files:**
- Modify: `UI_API/static/recommendation.js`

- [ ] **Step 1：修改 `showPushCard` 簽名接收 `styleKey`, `styleLabel`，label 改動態文字，動畫改單次，回傳 Promise**

把整個 `showPushCard` 函式替換為：

```js
  // ── 為您推薦跑馬燈（#recommendTicker）──
  // 回傳 Promise，在跑馬燈播完並淡出後 resolve。
  function showPushCard(items, reason, ollamaResult, styleKey, styleLabel) {
    if (!isPosActive() || !ui.recommendTicker) return Promise.resolve();
    const itemList = (Array.isArray(items) ? items : [items]).filter(Boolean).slice(0, 3);
    if (!itemList.length) return Promise.resolve();

    clearTicker();

    const names = itemList.map(i => i.name || '').filter(Boolean).join('、');
    const total = itemList.reduce((s, item) => s + Number(item.price || 0), 0);
    const priceText = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
    const finalText = _extractReason(ollamaResult) || reason || '';
    const scrollText = [names, finalText, priceText].filter(Boolean).join('　·　');

    const bar = document.createElement('div');
    bar.className = 'recommend-ticker-bar';

    // 左側標籤（動態風格文字）
    const label = document.createElement('span');
    label.className = 'recommend-ticker-label';
    label.dataset.style = styleKey || 'popular';
    label.textContent = styleLabel || '⭐ 為您推薦';

    // 滾動文字區
    const scrollWrap = document.createElement('div');
    scrollWrap.className = 'recommend-ticker-scroll';
    const scrollEl = document.createElement('span');
    scrollEl.className = 'recommend-ticker-text';
    scrollEl.textContent = scrollText;
    scrollWrap.appendChild(scrollEl);

    // 加入按鈕
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'recommend-ticker-add';
    const cartIcon = document.createElement('i');
    cartIcon.className = 'fas fa-cart-plus';
    addBtn.appendChild(cartIcon);
    addBtn.appendChild(document.createTextNode(' 加入'));

    // 關閉按鈕
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

    // 回傳 Promise：跑馬燈動畫結束（或逾時）後 resolve
    return new Promise((resolve) => {
      function finish() {
        if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
        clearTicker();
        resolve();
      }

      addBtn.onclick = () => {
        itemList.forEach(item => addToCart(item));
        finish();
      };
      closeBtn.onclick = finish;

      // 動畫播完自動結束（18s）
      scrollEl.addEventListener('animationend', finish, { once: true });
      // 保底逾時（動畫若因隱藏頁面暫停則觸發此）
      dismissTimer = setTimeout(finish, 19500);
    });
  }
```

- [ ] **Step 2：修改 `displayRecommendation` 傳入 style 並回傳 Promise**

找到：
```js
  function displayRecommendation(data) {
    const features = getFeatures();
    if (!features.recommend || !isPosActive()) return;
    const ids = data.recommendation_ids || [];
    if (!ids.length) return;
    const items = findMenuItems(ids);
    if (!items.length) return;
    showPushCard(items, data.reason || '', data.ollama_result || '');
    items.forEach(item => sessionPushedIds.add(item.id));
  }
```

改成：
```js
  function displayRecommendation(data) {
    const features = getFeatures();
    if (!features.recommend || !isPosActive()) return Promise.resolve();
    const ids = data.recommendation_ids || [];
    if (!ids.length) return Promise.resolve();
    const items = findMenuItems(ids);
    if (!items.length) return Promise.resolve();
    items.forEach(item => sessionPushedIds.add(item.id));
    return showPushCard(
      items,
      data.reason || '',
      data.ollama_result || '',
      data.recommendation_style || 'popular',
      data.recommendation_label || '⭐ 為您推薦',
    );
  }
```

- [ ] **Step 3：確認 `createRecommendationManager` 的 return 物件包含 `displayRecommendation`（已有，無需改）**

```bash
grep -n "displayRecommendation" UI_API/static/recommendation.js
```

預期看到 return 物件中有 `displayRecommendation`。

- [ ] **Step 4：語法檢查**

```bash
node --check UI_API/static/recommendation.js
echo "OK"
```

- [ ] **Step 5：Commit**

```bash
git add UI_API/static/recommendation.js
git commit -m "feat: showPushCard 回傳 Promise、動態 style label、單次動畫"
```

---

## Task 5：JS app.js — 閒置偵測 + 翻書換頁 + async 推播循環

**Files:**
- Modify: `UI_API/static/app.js`

### 5-A：閒置偵測

- [ ] **Step 1：在全域變數區（約第 60–75 行）新增 `lastInteractionAt`**

找到 `let interactionModalTimer = null;`（約第 71 行），在其後新增：

```js
let lastInteractionAt = Date.now();
```

- [ ] **Step 2：在 POS 初始化時（`initPOS` 函式內，或 `DOMContentLoaded` callback 內）綁定 pointer/touch 事件重設計時**

找到 `initPOS` 函式（搜尋 `function initPOS`），在函式體最前面加：

```js
  // 閒置偵測：任何觸控 / 點擊都重設計時
  document.addEventListener('pointerdown', () => { lastInteractionAt = Date.now(); }, { passive: true });
  document.addEventListener('touchstart',  () => { lastInteractionAt = Date.now(); }, { passive: true });
```

- [ ] **Step 3：在 `showScenarioRecommendationCard` 加閒置 15 秒門檻**

找到 `showScenarioRecommendationCard` 函式開頭的 guards（約第 1112–1117 行）：

```js
async function showScenarioRecommendationCard(intervention = {}, barrierResult = {}) {
  if (!isPosActive() || !ui.floatPush) return;
  if (_isVoiceActive()) return;   // 語音進行中不顯示
```

在 `if (_isVoiceActive()) return;` 後面加一行：

```js
  if (Date.now() - lastInteractionAt < 15000) return;   // 閒置未滿 15 秒，不打擾
```

### 5-B：翻書換頁特效

- [ ] **Step 4：把 `render` 函式拆成 `buildCard(items)` + `renderWithFlip(items)`**

目前 `showScenarioRecommendationCard` 內有一個 `render(items)` 函式。把它拆成兩段。

**先找到 `render` 函式整體**（從 `function render(items = []) {` 到對應的 `}`，約第 1151–1210 行）。

**替換整個 `render` 函式為以下兩個函式：**

```js
  // 純 DOM 建構，不修改 floatPush，回傳 card element
  function buildCard(items = []) {
    const itemList = items.filter(Boolean).slice(0, 3);
    const names = itemList.map(i => i.name || '').filter(Boolean).join('、') || '熱門餐點';
    const total = itemList.reduce((s, i) => s + Number(i.price || 0), 0);

    const card = document.createElement('div');
    card.className = 'push-card';

    const header = document.createElement('div');
    header.className = 'push-card-header';
    const titleEl = document.createElement('span');
    titleEl.className = 'push-card-title';
    titleEl.textContent = '還在猶豫嗎？';
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button'; closeBtn.className = 'push-close-btn'; closeBtn.setAttribute('aria-label', '關閉');
    const closeIcon = document.createElement('i'); closeIcon.className = 'fas fa-times';
    closeBtn.appendChild(closeIcon);
    header.append(titleEl, closeBtn);

    const nameEl = document.createElement('div');
    nameEl.className = 'push-item-names'; nameEl.textContent = names;

    const reasonEl = document.createElement('p');
    reasonEl.className = 'push-reason';
    reasonEl.textContent = String(intervention.tts_text || '我可以推薦幾個熱門選擇給您。');

    const btnGrid = document.createElement('div');
    btnGrid.className = 'grid gap-2';

    if (total) {
      const priceEl = document.createElement('div');
      priceEl.className = 'push-item-price';
      priceEl.textContent = itemList.length > 1 ? `組合 $${total}` : `$${Number(itemList[0].price || 0)}`;
      card.append(header, nameEl, priceEl, reasonEl, btnGrid);
    } else {
      card.append(header, nameEl, reasonEl, btnGrid);
    }

    const addBtn = _makeBtn('加入推薦餐點', 'push-add-btn btn-primary', 'fas fa-cart-plus');
    addBtn.addEventListener('click', () => {
      _clearScenarioTimer();
      itemList.forEach(item => trackedAddToCart(item, { source: 'scenario_recommendation' }));
      showPushNotice('已加入推薦餐點');
    });
    const refreshBtn = _makeBtn('換一個推薦', 'push-add-btn', null);
    refreshBtn.addEventListener('click', () => renderWithFlip());   // 翻書換頁
    const voiceBtn = _makeBtn('語音模式', 'push-add-btn', 'fas fa-microphone');
    voiceBtn.addEventListener('click', () => {
      _clearScenarioTimer(); clearAllPushCards();
      startAskRecording(document.getElementById('voiceAssistBtn'));
    });
    btnGrid.append(addBtn, refreshBtn, voiceBtn);

    // close button 事件（需要 card 已在 DOM 中可存取 _clearScenarioTimer）
    closeBtn.addEventListener('click', () => { _clearScenarioTimer(); clearAllPushCards(); });

    return card;
  }

  // 翻書特效換入新卡（換一個按鈕 & 初次顯示皆呼叫此函式）
  async function renderWithFlip(items) {
    if (!items) items = await resolveItems();
    const newCard = buildCard(items);

    const oldCard = ui.floatPush.firstElementChild;
    if (oldCard && oldCard.classList.contains('push-card')) {
      oldCard.classList.add('push-card-flip-out');
      await new Promise(r => setTimeout(r, 220));
    }

    ui.floatPush.replaceChildren(newCard);
    // 移除舊的 slide-up 動畫，改用 flip-in
    newCard.style.animation = 'none';
    newCard.classList.add('push-card-flip-in');

    _clearScenarioTimer();
    _scenarioCardTimer = setTimeout(() => { _scenarioCardTimer = null; clearAllPushCards(); }, 10000);
  }
```

- [ ] **Step 5：把函式最後的 `render(await resolveItems())` 改為 `renderWithFlip(await resolveItems())`**

找到（約第 1212 行）：
```js
  render(await resolveItems());
```

改成：
```js
  await renderWithFlip(await resolveItems());
```

### 5-C：async 推播循環

- [ ] **Step 6：把全域 `recommendLoopId` 的語義從 `intervalId` 改為 `boolean` flag**

找到全域變數區的：
```js
let recommendLoopId = null;
```

改成：
```js
let recommendLoopActive = false;   // true = 循環正在運行中
```

> **注意**：`recommendLoopId` 在 `app.js` 共有以下幾處使用，全部一起改：
> - 第 288 行：`if (recommendLoopId) clearInterval(recommendLoopId);`  → `recommendLoopActive = false;`
> - 第 291 行：`recommendLoopId = null;`  → `recommendLoopActive = false;`
> - 第 1685 行：`if (isAdminMode() || recommendLoopId) return;`  → `if (isAdminMode() || recommendLoopActive) return;`
> - 第 1686 行：`recommendLoopId = setInterval(...)` → 整段替換（Step 7）
> - 第 1974 行：`if (recommendLoopId) clearInterval(recommendLoopId);`  → `recommendLoopActive = false;`

在 `restartLoops` 函式（第 285 行）：
```js
function restartLoops() {
  if (emotionLoopId) clearInterval(emotionLoopId);
  if (detectionLoopId) clearInterval(detectionLoopId);
  if (recommendLoopId) clearInterval(recommendLoopId);
  emotionLoopId = null;
  detectionLoopId = null;
  recommendLoopId = null;
```

改成：
```js
function restartLoops() {
  if (emotionLoopId) clearInterval(emotionLoopId);
  if (detectionLoopId) clearInterval(detectionLoopId);
  recommendLoopActive = false;
  emotionLoopId = null;
  detectionLoopId = null;
```

- [ ] **Step 7：把 `startRecommendLoop` 改為 async 遞迴 loop，播完 ticker 再等 10 秒**

找到整個 `startRecommendLoop` 函式：
```js
function startRecommendLoop() {
  if (isAdminMode() || recommendLoopId) return;
  recommendLoopId = setInterval(async () => {
    if (!isPosActive() || recommendPending) return;
    if (document.hidden) return;
    await fetchAndDisplayRecommend();
  }, Math.max(10, Number(perfValue('RECOMMEND_INTERVAL_SEC')) || 30) * 1000);
}
```

整段替換為：
```js
async function startRecommendLoop() {
  if (isAdminMode() || recommendLoopActive) return;
  recommendLoopActive = true;

  const initialDelay = Math.max(10, Number(perfValue('RECOMMEND_INTERVAL_SEC')) || 10) * 1000;

  while (recommendLoopActive) {
    // 等待間隔（首次或上次播完後各等 10 秒）
    await new Promise(r => setTimeout(r, initialDelay));
    if (!recommendLoopActive) break;
    if (!isPosActive() || document.hidden || recommendPending) continue;

    // 取推薦並等跑馬燈播完
    const tickerDone = await fetchAndDisplayRecommend();
    if (tickerDone && recommendLoopActive) await tickerDone;
  }
}
```

- [ ] **Step 8：修改 `fetchAndDisplayRecommend` 回傳 `displayRecommendation` 的 Promise**

找到 `fetchAndDisplayRecommend` 函式（約第 1656 行），目前 `displayRecommendation(data)` 沒有使用回傳值。把這一行：

```js
    if (data.status === 'success') displayRecommendation(data);
```

改成：

```js
    if (data.status === 'success') return displayRecommendation(data);
```

同時讓函式在 try 外部有 fallback return（避免 undefined）：

找到 `fetchAndDisplayRecommend` 的 `finally` block 結尾 `}`，確認整個函式如下（僅修改 return 一行，其餘不動）：

```js
async function fetchAndDisplayRecommend() {
  const f = getFeatures();
  if (!f.recommend) return;
  if (recommendRequestInFlight) return;
  if (_isVoiceActive()) return;
  if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) return;
  if (document.querySelector('.cart-shell')?.classList.contains('kiosk-cart-open')) return;
  if (Date.now() < promotionPausedUntil) return;
  if (interactionModalTimer) { clearTimeout(interactionModalTimer); interactionModalTimer = null; }
  const fd = new FormData();
  fd.append('session_id', sessionId);
  const ctrl = new AbortController();
  const tid = setTimeout(() => ctrl.abort(), 12000);
  recommendRequestInFlight = true;
  recommendPending = true;
  try {
    const data = await api.autoRecommend(fd, ctrl.signal);
    if (data.status === 'success') return displayRecommendation(data);   // ← 加 return
  } catch (err) {
    console.warn('[auto_recommend failed]', err);
  } finally {
    clearTimeout(tid);
    recommendRequestInFlight = false;
    recommendPending = false;
  }
}
```

- [ ] **Step 9：語法檢查**

```bash
node --check UI_API/static/app.js
echo "OK"
```

預期：`OK`（無語法錯誤）

- [ ] **Step 10：Commit**

```bash
git add UI_API/static/app.js
git commit -m "feat: 閒置 15s 門檻、翻書換頁、async ticker 循環"
```

---

## Task 6：整合驗證

- [ ] **Step 1：啟動主服務確認無啟動錯誤**

```bash
cd UI_API && python3 -m py_compile main.py config.py ai_services.py
python3 -m py_compile routes/recommendation_routes.py services/recommendation_service.py
echo "全部 OK"
```

- [ ] **Step 2：curl 確認 API 回傳含 style 欄位**

```bash
curl -s -X POST http://127.0.0.1:8000/api/auto_recommend \
  -F "session_id=test_plan" | python3 -m json.tool | grep -E "recommendation_style|recommendation_label|status"
```

預期輸出（風格依輪次不同）：
```json
"recommendation_style": "popular",
"recommendation_label": "⭐ 人氣組合",
"status": "success"
```

- [ ] **Step 3：瀏覽器驗證 — 閒置 15 秒**

1. 開 `http://127.0.0.1:8000`，開啟 POS 模式
2. 完全不操作 15 秒
3. 觀察「還在猶豫嗎？」卡片自動彈出、且卡片明顯比之前大（寬度 ~520px）

- [ ] **Step 4：瀏覽器驗證 — 翻書換頁**

1. 讓「還在猶豫嗎？」卡片顯示
2. 點「換一個推薦」
3. 觀察：舊卡片向右旋轉消失 (0.22s) → 新卡片從左旋轉進入 (0.22s)，無閃爍

- [ ] **Step 5：瀏覽器驗證 — 跑馬燈循環**

1. 觸發一次推播（可從後台 Demo 觸發，或等自動循環）
2. 觀察跑馬燈播到底後自動淡出
3. 等 10 秒後第二條跑馬燈出現
4. 檢查 label 標籤文字是否輪替（⭐/🥗/😈/💰）

- [ ] **Step 6：最終 commit**

```bash
git add -A
git commit -m "feat: AI推播 UX 升級完成 - 閒置門檻/放大/翻書/循環/多樣推薦"
```
