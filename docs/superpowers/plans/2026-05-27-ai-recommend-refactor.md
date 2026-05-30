# AI 推播跑馬燈重構 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 刪除舊推播系統的 A/B 測試、風格輪換、複雜 coerce 邏輯；改為「按下開始點餐後在菜單下方以跑馬燈顯示 AI 推薦，每次跑馬燈播完 → 等 10 秒 → 下一次」。

**Architecture:** 後端 `generate_recommendation()` 直接呼叫 Ollama 並校驗 ID 白名單；前端 `startRecommendLoop()` 採 await-marquee-then-sleep 循環，不依賴計時器間隔；`recommendation.js` 的 `showPushCard()` 去除 styleKey/styleLabel 參數，仍回傳 Promise（跑馬燈結束時 resolve）。

**Tech Stack:** Python/FastAPI, Vanilla JS, Ollama (qwen3.5:4b), node --check / py_compile 語法驗證

---

## File Map

| 狀態 | 路徑 | 說明 |
|------|------|------|
| Modify | `UI_API/services/recommendation_service.py` | 刪除 `_RECOMMENDATION_STYLES`、`coerce_recommendation`、`align_recommendation_reason`、`_build_recommendation_copy`；改寫 `generate_recommendation` |
| Modify | `UI_API/routes/recommendation_routes.py` | 移除 `get_default_recommendation` 匯入與備用邏輯中 `mode` 欄位；精簡成功路徑 |
| Modify | `UI_API/config.py` | 從 `DEFAULT_SETTINGS` 與 `PUBLIC_SETTINGS_KEYS` 刪除 7 個廢棄鍵 |
| Modify | `UI_API/routes/emotion_routes.py` | 移除 `influence_recommend` 欄位 |
| Modify | `UI_API/learning_data/settings.json` | 同步刪除廢棄鍵 |
| Modify | `UI_API/static/recommendation.js` | 精簡 `showPushCard`（移除 style 參數）、移除 `_extractReason` |
| Modify | `UI_API/static/app.js` | 改寫 `startRecommendLoop`、`fetchAndDisplayRecommend`；移除廢棄變數與管理員 UI 綁定 |
| Modify | `UI_API/index.html` | 移除「推播最短間隔」input div |

---

## Task 1：精簡 recommendation_service.py（後端核心）

**Files:**
- Modify: `UI_API/services/recommendation_service.py`

- [ ] **Step 1：刪除 A/B 與風格輪換基礎設施**

  在檔案頂端，刪除以下整段（第 14–35 行）：

  ```python
  # 刪除這整段
  _RECOMMENDATION_STYLES = itertools.cycle([
      { "key": "popular", ... },
      { "key": "diet", ... },
      { "key": "evil_combo", ... },
      { "key": "value", ... },
  ])
  ```

  同時移除 `import itertools`（第 2 行），因為整個檔案不再需要它。

- [ ] **Step 2：刪除 coerce_recommendation、align_recommendation_reason、_build_recommendation_copy**

  刪除下列三個函式（約第 304–405 行）：
  - `coerce_recommendation(result, menu_ids, menu_items=None) -> dict`
  - `align_recommendation_reason(reason, recommendation_ids, menu_items) -> str`
  - `_build_recommendation_copy(selected_items) -> str`

  注意：`get_default_recommendation()` **保留**（voice_assist_service 需要它）。

- [ ] **Step 3：改寫 generate_recommendation**

  以下面的完整函式取代舊版 `generate_recommendation`（原第 434–471 行）：

  ```python
  async def generate_recommendation(session_id: str, ollama_semaphore) -> dict:  # noqa: ARG001
      """呼叫 Ollama 推薦餐點，回傳 {status, recommendation_ids, reason}。"""
      full_menu_context, rag_context = await asyncio.gather(
          asyncio.to_thread(database.build_full_menu_context),
          asyncio.to_thread(database.retrieve_menu_from_rag, "推薦餐點"),
      )
      user_prompt = (
          f"{full_menu_context}\n\n"
          f"【RAG 補充規則與知識】\n{rag_context or '（無補充）'}\n\n"
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
          return {"status": "error", "message": raw.get("error", "unknown")}

      raw_ids = raw.get("recommendation_ids") or []
      if isinstance(raw_ids, str):
          raw_ids = [raw_ids]
      cleaned_ids = []
      for raw_id in raw_ids:
          menu_id = clean_menu_id(raw_id, menu_ids)
          if menu_id and menu_id not in cleaned_ids:
              cleaned_ids.append(menu_id)
      if not cleaned_ids:
          cleaned_ids = [menu_ids[0]] if menu_ids else []

      return {
          "status": "success",
          "recommendation_ids": cleaned_ids[:3],
          "reason": str(raw.get("reason") or "這是根據菜單為您挑選的餐點。").strip(),
      }
  ```

- [ ] **Step 4：語法驗證**

  ```bash
  python3 -m py_compile UI_API/services/recommendation_service.py
  echo "OK"
  ```

  預期：印出 `OK`，無任何錯誤輸出。

---

## Task 2：精簡 recommendation_routes.py

**Files:**
- Modify: `UI_API/routes/recommendation_routes.py`

- [ ] **Step 1：以下列完整內容取代整個檔案**

  ```python
  """AI 推播路由：/api/auto_recommend，失敗時回預設熱門。"""
  import asyncio

  from fastapi import APIRouter, Form

  from repositories import menu_repository
  from services import recommendation_service


  def create_router(deps: dict) -> APIRouter:
      router = APIRouter(prefix="/api", tags=["recommendation"])

      @router.post("/auto_recommend")
      async def process_auto_recommend(session_id: str = Form(...)):
          try:
              response = await recommendation_service.generate_recommendation(
                  session_id=session_id,
                  ollama_semaphore=deps["ollama_semaphore"],
              )
              if response.get("status") == "success":
                  return response
          except Exception as e:
              print(f"❌ auto_recommend 錯誤: {e}")
          menu_items = await asyncio.to_thread(menu_repository.get_menu)
          return recommendation_service.get_default_recommendation(menu_items)

      return router
  ```

- [ ] **Step 2：語法驗證**

  ```bash
  python3 -m py_compile UI_API/routes/recommendation_routes.py
  echo "OK"
  ```

  預期：印出 `OK`。

---

## Task 3：清理 config.py、emotion_routes.py、settings.json

**Files:**
- Modify: `UI_API/config.py`
- Modify: `UI_API/routes/emotion_routes.py`
- Modify: `UI_API/learning_data/settings.json`

- [ ] **Step 1：從 DEFAULT_SETTINGS 刪除 7 個廢棄鍵**

  在 `UI_API/config.py` 的 `DEFAULT_SETTINGS` 中，刪除以下行：

  ```python
  "EMOTION_INFLUENCE_RECOMMEND": False,        # 刪除
  "RECOMMEND_INTERVAL_SEC": 10,                # 刪除
  "RECOMMEND_AFTER_ASK_DELAY_MS": 1200,        # 刪除
  "AUTO_RECOMMEND_MIN_GAP_SEC": 8,             # 刪除
  "ENABLE_RECOMMEND_CACHE": True,              # 刪除
  "AB_SINGLE_CALL": True,                      # 刪除
  "RECOMMEND_SYSTEM_PROMPT_B": (...),          # 刪除（多行字串，第 163–175 行）
  ```

  `RECOMMEND_SYSTEM_PROMPT` 和 `USE_AI_RECOMMEND` **保留**。

- [ ] **Step 2：從 PUBLIC_SETTINGS_KEYS 刪除 3 個廢棄鍵**

  在 `PUBLIC_SETTINGS_KEYS` set 中，刪除：

  ```python
  "RECOMMEND_INTERVAL_SEC",         # 刪除
  "RECOMMEND_AFTER_ASK_DELAY_MS",   # 刪除
  "AUTO_RECOMMEND_MIN_GAP_SEC",     # 刪除
  ```

- [ ] **Step 3：移除 emotion_routes.py 的 influence_recommend 欄位**

  在 `UI_API/routes/emotion_routes.py`，找到：

  ```python
  "influence_recommend": bool(config.get("EMOTION_INFLUENCE_RECOMMEND", True)),
  ```

  刪除此行（包含行尾逗號）。

- [ ] **Step 4：同步清理 settings.json**

  在 `UI_API/learning_data/settings.json` 中，刪除以下鍵（每行含逗號）：

  - `"EMOTION_INFLUENCE_RECOMMEND": true,`
  - `"RECOMMEND_INTERVAL_SEC": 10,`
  - `"RECOMMEND_AFTER_ASK_DELAY_MS": 1200,`
  - `"AUTO_RECOMMEND_MIN_GAP_SEC": 8,`
  - `"ENABLE_RECOMMEND_CACHE": false,`
  - `"AB_SINGLE_CALL": true,`
  - `"RECOMMEND_SYSTEM_PROMPT_B": "..."` （多行，找到整個鍵值對刪除）

- [ ] **Step 5：語法驗證**

  ```bash
  python3 -m py_compile UI_API/config.py UI_API/routes/emotion_routes.py
  python3 -c "import json; json.load(open('UI_API/learning_data/settings.json'))" && echo "settings.json OK"
  ```

  預期：兩行都顯示 `OK`（第一行無輸出代表通過，第二行印出 `settings.json OK`）。

---

## Task 4：精簡 recommendation.js

**Files:**
- Modify: `UI_API/static/recommendation.js`

- [ ] **Step 1：以下列完整內容取代整個檔案**

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

    function clearTicker() {
      if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
      if (!ui.recommendTicker) return;
      if (currentTicker) {
        currentTicker.classList.add('ticker-fade-out');
        const t = currentTicker;
        currentTicker = null;
        setTimeout(() => { t.remove(); ui.recommendTicker.replaceChildren(); }, 400);
      } else {
        ui.recommendTicker.replaceChildren();
      }
    }

    function clearAllPushCards() {
      clearTicker();
      ui.floatPush?.replaceChildren();
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

      clearTicker();

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
        function finish() {
          if (dismissTimer) { clearTimeout(dismissTimer); dismissTimer = null; }
          clearTicker();
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

    return { showPushCard, clearAllPushCards, displayRecommendation, showPushNotice };
  }
  ```

- [ ] **Step 2：語法驗證**

  ```bash
  node --check UI_API/static/recommendation.js && echo "OK"
  ```

  預期：印出 `OK`。

---

## Task 5：改寫 app.js 推播迴圈

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1：移除廢棄狀態變數**

  找到並刪除下列兩行（約第 55、60 行）：

  ```javascript
  let recommendPending = false;       // 刪除
  let recommendRequestInFlight = false; // 刪除
  ```

- [ ] **Step 2：移除 runtimeSettings 裡的廢棄預設值**

  找到並刪除（約第 251–252 行）：

  ```javascript
  RECOMMEND_INTERVAL_SEC: 10,          // 刪除
  RECOMMEND_AFTER_ASK_DELAY_MS: 1200,  // 刪除
  ```

- [ ] **Step 3：移除 resetSession 裡殘留的 recommendLoopActive = false 重設（只保留 beforeunload 的那一行）**

  找到 `resetSession` 函式（約第 285 行）中：

  ```javascript
  recommendLoopActive = false;
  ```

  確認此行是 `resetSession` 內部的，刪除它。（`beforeunload` handler 的那一行第 1911 行**保留**。）

- [ ] **Step 4：改寫 fetchAndDisplayRecommend**

  找到整個 `async function fetchAndDisplayRecommend()` 函式（約第 1581–1607 行），以下列內容取代：

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
      if (data.status === 'success') return displayRecommendation(data);
    } catch (err) {
      console.warn('[auto_recommend failed]', err);
    } finally {
      clearTimeout(tid);
    }
  }
  ```

- [ ] **Step 5：改寫 startRecommendLoop**

  找到整個 `async function startRecommendLoop()` 函式（約第 1609–1620 行），以下列內容取代：

  ```javascript
  async function startRecommendLoop() {
    if (isAdminMode() || recommendLoopActive) return;
    recommendLoopActive = true;
    while (recommendLoopActive) {
      if (!isPosActive() || document.hidden) {
        await new Promise(r => setTimeout(r, 1000));
        continue;
      }
      const tickerDone = await fetchAndDisplayRecommend();
      if (tickerDone && recommendLoopActive) await tickerDone;
      if (recommendLoopActive) await new Promise(r => setTimeout(r, 10_000));
    }
  }
  ```

- [ ] **Step 6：移除 trigger_recommend 延遲觸發區塊**

  找到並刪除（約第 1791–1795 行）：

  ```javascript
  if (data.trigger_recommend && getFeatures().recommend) {
    setTimeout(async () => {
      await fetchAndDisplayRecommend();
    }, Number(perfValue('RECOMMEND_AFTER_ASK_DELAY_MS')) || 1200);
  }
  ```

- [ ] **Step 7：移除 applyPerformancePreset 中的 recommend 欄位**

  找到（約第 1968–1979 行）：

  ```javascript
  function applyPerformancePreset(mode) {
    const presets = {
      eco:      { emotion: 30, record: 700,  recommend: 60, tokens: 160, rag: 2 },
      balanced: { emotion: 15, record: 900,  recommend: 30, tokens: 220, rag: 3 },
      quality:  { emotion: 8,  record: 1500, recommend: 18, tokens: 360, rag: 4 }
    };
    const p = presets[mode] || presets.balanced;
    document.getElementById('inp-emotion-interval').value = p.emotion;
    document.getElementById('inp-emotion-record-ms').value = p.record;
    document.getElementById('inp-recommend-interval').value = p.recommend;   // ← 刪除這行
    document.getElementById('inp-num-predict').value = p.tokens;
    document.getElementById('inp-rag-top-k').value = p.rag;
  }
  ```

  只刪除 `document.getElementById('inp-recommend-interval').value = p.recommend;` 這一行。
  同時從 presets 物件移除 `recommend:` 欄位（三行各刪一個 `recommend: N,`）。

- [ ] **Step 8：移除管理員 UI 的 RECOMMEND_INTERVAL_SEC 讀寫**

  找到 `loadEmotionSettings` 函式中（約第 2336 行）：

  ```javascript
  set('inp-recommend-interval', fullSettings.RECOMMEND_INTERVAL_SEC ?? 30);
  ```

  刪除此行。

  找到 `saveEmotionSettings` 函式中（約第 2384 行）：

  ```javascript
  fullSettings.RECOMMEND_INTERVAL_SEC    = flt('inp-recommend-interval', '30');
  ```

  刪除此行。

- [ ] **Step 9：語法驗證**

  ```bash
  node --check UI_API/static/app.js && echo "OK"
  ```

  預期：印出 `OK`。

---

## Task 6：移除 HTML admin 輸入欄位 + 整體驗證 + Commit

**Files:**
- Modify: `UI_API/index.html`

- [ ] **Step 1：從 index.html 刪除推播間隔 input div**

  找到下列整段（約第 370–374 行），整段刪除：

  ```html
  <div>
    <label style="font-size:11px;color:#64748b;display:block;margin-bottom:3px">推播最短間隔（秒）</label>
    <input id="inp-recommend-interval" type="number" style="width:100%;border:1px solid #e2e8f0;border-radius:6px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;box-sizing:border-box" />
  </div>
  ```

- [ ] **Step 2：全域殘留掃描**

  確認沒有殘留引用：

  ```bash
  grep -rn "RECOMMEND_INTERVAL_SEC\|RECOMMEND_AFTER_ASK_DELAY_MS\|AUTO_RECOMMEND_MIN_GAP_SEC\|ENABLE_RECOMMEND_CACHE\|AB_SINGLE_CALL\|RECOMMEND_SYSTEM_PROMPT_B\|EMOTION_INFLUENCE_RECOMMEND\|recommendation_style\|recommendation_label\|_RECOMMENDATION_STYLES\|coerce_recommendation\|align_recommendation_reason\|_build_recommendation_copy\|inp-recommend-interval\|recommendPending\|recommendRequestInFlight" \
    UI_API/ --include="*.py" --include="*.js" --include="*.html" \
    | grep -v "settings.json"
  ```

  預期：無任何輸出。若有輸出，逐一處理後再繼續。

- [ ] **Step 3：完整語法驗證**

  ```bash
  python3 -m py_compile \
    UI_API/config.py \
    UI_API/routes/recommendation_routes.py \
    UI_API/routes/emotion_routes.py \
    UI_API/services/recommendation_service.py && \
  node --check UI_API/static/app.js && \
  node --check UI_API/static/recommendation.js && \
  echo "ALL OK"
  ```

  預期：最後一行印出 `ALL OK`。

- [ ] **Step 4：Commit**

  ```bash
  git add -f \
    UI_API/services/recommendation_service.py \
    UI_API/routes/recommendation_routes.py \
    UI_API/config.py \
    UI_API/routes/emotion_routes.py \
    UI_API/learning_data/settings.json \
    UI_API/static/recommendation.js \
    UI_API/static/app.js \
    UI_API/index.html
  git commit -m "refactor: AI 推播改為跑馬燈迴圈，移除 A/B 測試與風格輪換

  - recommendation_service: 刪除 _RECOMMENDATION_STYLES / coerce_recommendation /
    align_recommendation_reason / _build_recommendation_copy，改寫 generate_recommendation
  - recommendation_routes: 精簡成功/失敗路徑
  - config: 移除 7 個廢棄設定鍵（RECOMMEND_INTERVAL_SEC 等）
  - app.js: startRecommendLoop 改為 await-marquee-then-10s 循環
  - recommendation.js: showPushCard 移除 styleKey/styleLabel 參數

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
  ```

---

## Self-Review

**Spec coverage check:**
- ✅ 按下開始點餐後啟動 → `startRecommendLoop()` 在 `startSystemBtn` click handler 呼叫（已存在，Task 5 改寫其內容）
- ✅ 跑馬燈在菜單下方 → `#recommendTicker` 已在 index.html 存在於正確位置
- ✅ Ollama 推薦 → `generate_recommendation` 呼叫 `ai_services.ask_ollama`
- ✅ 等跑馬燈播完 → `showPushCard` 回傳 Promise，`startRecommendLoop` 中 `await tickerDone`
- ✅ 等 10 秒 → `await new Promise(r => setTimeout(r, 10_000))`
- ✅ 下次推薦 → while loop 繼續

**Placeholder scan:** 無 TBD/TODO，所有程式碼區塊均為完整可執行內容。

**Type consistency:**
- `showPushCard(items, reason)` — Task 4 定義，Task 5 的 `displayRecommendation` 呼叫 `showPushCard(items, data.reason || '')` ✅
- `generate_recommendation` 回傳 `{status, recommendation_ids, reason}` — Task 1 定義，Task 2 路由讀取 `response.get("status")` ✅
- `displayRecommendation(data)` — Task 4 定義，Task 5 的 `fetchAndDisplayRecommend` 呼叫 `displayRecommendation(data)` ✅
- `createRecommendationManager` 的解構參數：Task 4 移除了 `escapeHTML`，需確認 app.js 呼叫端也沒傳它（Task 5 沒動這一段，需檢查）

  ⚠️ **額外步驟**：在 Task 4 Step 2 之後，確認 `app.js` 中 `createRecommendationManager({...})` 的呼叫端（約第 573–586 行）沒有傳遞 `escapeHTML` 參數。若有，一併刪除該參數傳遞（這是無害的多餘傳入，但保持乾淨）。
