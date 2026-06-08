# 結帳倒數付款 Modal + Emotion-LLaMA 整合 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將結帳畫面的「在此快速結帳」改為含 15 秒倒數的付款 modal，逾時顯示付款失敗 + 人員協助按鈕，並整合 Emotion-LLaMA 在倒數中觸發情緒分析、由 Ollama 生成協助語顯示於協助畫面。

**Architecture:** 前端 vanilla JS 狀態機驅動 modal（counting → failed → notified）；倒數中於「剩餘 = 15 − clip_sec」秒觸發 `analyzeEmotionEvent`（fire-and-forget，存 promise 結果）；後端 `emotion_service` 對 `payment_timeout` 事件在情緒提取後額外呼叫 Ollama 生成協助語，隨 HTTP 回應返回前端。Admin 新增開關控制此事件，預設開啟。

**Tech Stack:** FastAPI（Python）、Vanilla JS（ES modules）、Ollama（qwen3.5:4b）、Emotion-LLaMA（Gradio HTTP）。

**驗證方式：** 本專案無測試框架。每個 task 以 `python3 -m py_compile`（Python）/ `node --check`（JS）做語法驗證，最後以執行 app 手動驗證行為。

---

### Task 1: 後端設定 — 新增 payment_timeout 開關與事件標籤

**Files:**
- Modify: `UI_API/config.py`（`DEFAULT_SETTINGS` emotion 區塊 + `PUBLIC_SETTINGS_KEYS`）
- Modify: `UI_API/backend/services/emotion_service.py:18`（`EVENT_TYPE_LABELS`）

- [ ] **Step 1: 在 config.py 的 emotion 設定區塊新增 key**

在 `DEFAULT_SETTINGS` 內 `"EMOTION_LLAMA_EVENT_CANCEL_GUIDE": False,` 之後新增一行：

```python
    "EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT": True,  # 付款倒數逾時觸發分析（預設開啟）
```

- [ ] **Step 2: 將該 key 加入 PUBLIC_SETTINGS_KEYS**

在 `PUBLIC_SETTINGS_KEYS` 集合中，`"EMOTION_LLAMA_EVENT_CANCEL_GUIDE",` 之後新增：

```python
    "EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT",
```

（若 `EMOTION_LLAMA_EVENT_CANCEL_GUIDE` 不在集合中，則加在 `EMOTION_LLAMA_EVENT_TUTORIAL` 之後即可——目標是讓 POS 的 `/api/public_settings` 能讀到此 key。）

- [ ] **Step 3: 在 emotion_service.py 新增事件標籤**

將 `EVENT_TYPE_LABELS` 改為：

```python
EVENT_TYPE_LABELS = {
    "tutorial_popup": "如何點餐彈跳視窗",
    "voice_mode": "語音模式",
    "cancel_guide": "需要幫助彈跳視窗",
    "payment_timeout": "付款逾時協助",
}
```

- [ ] **Step 4: 語法驗證**

Run: `cd UI_API && python3 -m py_compile config.py backend/services/emotion_service.py`
Expected: 無輸出（成功）

- [ ] **Step 5: Commit**

```bash
git add UI_API/config.py UI_API/backend/services/emotion_service.py
git commit -m "feat(emotion): add payment_timeout event setting & label"
```

---

### Task 2: 後端 — Ollama 協助語生成

**Files:**
- Modify: `UI_API/backend/services/emotion_service.py`（`analyze_event` 新增 payment 分支 + 新函式 `_generate_payment_assist`）

- [ ] **Step 1: 在 analyze_event 中、`emotion_log_repository.append_log(entry)` 之前，新增 payment assist 生成**

找到 `analyze_event` 中建構 `entry` dict 之後、`emotion_log_repository.append_log(entry)` 之前的位置，插入：

```python
    # 付款逾時事件：情緒分析成功後，用 Ollama 生成協助語供前端「人員協助付款」顯示
    if (event_type == "payment_timeout"
            and not quality_skipped and not error
            and entry.get("emotion")):
        try:
            entry["assist_response"] = await _generate_payment_assist(entry)
        except Exception as e:
            print(f"⚠️ Payment assist Ollama 生成失敗: {e}")
```

- [ ] **Step 2: 新增 `_generate_payment_assist` 函式**

在 `_extract_emotion_via_ollama` 函式定義之後新增：

```python
async def _generate_payment_assist(entry: dict) -> str:
    """付款逾時：依情緒分析生成一句溫暖協助語（供前端「人員協助付款」顯示）。"""
    system = (
        "你是麥當勞自助點餐機的智能協助員。"
        "根據顧客的情緒分析，生成一句溫暖友善的協助語（繁體中文，20–40 字）。"
        "不要提及你在分析情緒或任何系統流程，用自然口語安慰付款遇到困難的顧客，"
        "並表示店員即將前來協助。"
        '只輸出 JSON：{"assist_message":"..."}'
    )
    user = (
        f"顧客情緒：{entry.get('emotion','')}（強度：{entry.get('intensity','')}）\n"
        f"表情：{entry.get('facial','')}\n"
        f"描述：{(entry.get('description','') or '')[:150]}\n"
        "請生成一句友善協助語。"
    )
    result = await asyncio.to_thread(
        ai_services.ask_ollama, system, user, "PAYMENT_ASSIST",
        config.get("MODEL_NAME", "qwen3.5:4b"), 80,
    )
    return str(result.get("assist_message") or "") if isinstance(result, dict) else ""
```

- [ ] **Step 3: 語法驗證**

Run: `cd UI_API && python3 -m py_compile backend/services/emotion_service.py`
Expected: 無輸出（成功）

- [ ] **Step 4: Commit**

```bash
git add UI_API/backend/services/emotion_service.py
git commit -m "feat(emotion): generate Ollama payment assist message on timeout"
```

---

### Task 3: Admin UI — 付款倒數逾時分析開關

**Files:**
- Modify: `UI_API/frontend/admin/admin.html`（觸發事件區塊）
- Modify: `UI_API/frontend/admin/admin.js`（`loadEmotionSettings` + `saveEmotionSettings`）

- [ ] **Step 1: 在 admin.html 觸發事件區塊新增 checkbox**

在「需要幫助嗎？」彈跳視窗那個 `<div>`（含 `inp-emotion-event-cancel-guide`）之後、該 `<div class="...觸發事件...">` 容器的收尾 `</div>` 之前，新增：

```html
            <div style="display:flex;align-items:center;gap:12px">
              <label style="min-width:200px;font-size:13px;color:var(--text2)">付款倒數逾時分析（預設開啟）</label>
              <input type="checkbox" id="inp-emotion-event-payment-timeout">
            </div>
```

- [ ] **Step 2: 在 admin.js `loadEmotionSettings` 讀取設定**

找到 `loadEmotionSettings` 中 `g('inp-emotion-event-cancel-guide').checked = ...` 那一行，於其後新增：

```javascript
    g('inp-emotion-event-payment-timeout').checked = s.EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT !== false;
```

（用 `!== false` 讓預設為開啟。）

- [ ] **Step 3: 在 admin.js `saveEmotionSettings` 寫入設定**

找到 `saveEmotionSettings` 中 body 物件的 `EMOTION_LLAMA_EVENT_CANCEL_GUIDE: ...,` 那一行，於其後新增：

```javascript
      EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT: g('inp-emotion-event-payment-timeout').checked,
```

- [ ] **Step 4: 語法驗證**

Run: `node --check /home/oliver/Project_2026/UI_API/frontend/admin/admin.js`
Expected: 無輸出（成功）

- [ ] **Step 5: Commit**

```bash
git add UI_API/frontend/admin/admin.html UI_API/frontend/admin/admin.js
git commit -m "feat(admin): add payment timeout emotion event toggle"
```

---

### Task 4: 移除「友善模式」

**Files:**
- Modify: `UI_API/frontend/pos/index.html`（payment footer）
- Modify: `UI_API/frontend/pos/app.js`（i18n keys + setKioskLanguage 賦值）
- Modify: `UI_API/frontend/shared/styles.css`（`.kiosk-payment-footer`）

- [ ] **Step 1: 移除 index.html 友善模式按鈕**

將 `kiosk-payment-footer` 區塊：

```html
      <div class="kiosk-payment-footer">
        <button id="kioskCancelOrderBtn" type="button">取消整單訂單</button>
        <button type="button">友善模式</button>
      </div>
```

改為：

```html
      <div class="kiosk-payment-footer">
        <button id="kioskCancelOrderBtn" type="button">取消整單訂單</button>
      </div>
```

- [ ] **Step 2: 移除 app.js 的 friendlyMode i18n keys**

刪除這兩行（zh 第 118 行、en 第 176 行附近）：

```javascript
    friendlyMode: '友善模式',
```
```javascript
    friendlyMode: 'Accessibility Mode',
```

- [ ] **Step 3: 移除 app.js setKioskLanguage 中的賦值**

刪除這兩行：

```javascript
  const friendlyBtn = document.querySelector('.kiosk-payment-footer button:nth-child(2)');
  if (friendlyBtn) friendlyBtn.textContent = kt('friendlyMode');
```

- [ ] **Step 4: 調整 styles.css footer 佈局為單按鈕**

找到 `.kiosk-payment-footer` 規則：

```css
  .kiosk-payment-footer {
    width: min(720px, 48vw) !important;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: clamp(18px, 2vw, 28px) !important;
    margin-top: auto;
  }
```

改為：

```css
  .kiosk-payment-footer {
    width: min(360px, 28vw) !important;
    display: flex;
    justify-content: center;
    margin-top: auto;
  }
```

- [ ] **Step 5: 語法驗證**

Run: `node --check /home/oliver/Project_2026/UI_API/frontend/pos/app.js`
Expected: 無輸出（成功）

- [ ] **Step 6: Commit**

```bash
git add UI_API/frontend/pos/index.html UI_API/frontend/pos/app.js UI_API/frontend/shared/styles.css
git commit -m "feat(pos): remove accessibility mode button from payment screen"
```

---

### Task 5: 付款倒數 Modal — HTML 結構

**Files:**
- Modify: `UI_API/frontend/pos/index.html`（在 `#kioskPaymentScreen` 區塊收尾後新增）
- Modify: `UI_API/frontend/shared/ui.js`（element map 註冊）

- [ ] **Step 1: 在 index.html 新增 modal markup**

在 `<div id="kioskPaymentScreen" ...>...</div>` 整個區塊的收尾 `</div>` 之後新增：

```html
  <!-- 付款倒數 Modal -->
  <div id="paymentCountdownBackdrop" class="payment-cd-backdrop hidden"></div>
  <div id="paymentCountdownModal" class="payment-cd-modal hidden" role="dialog" aria-modal="true" aria-label="付款處理中">

    <!-- 計時中 -->
    <div id="paymentCdCounting" class="payment-cd-section">
      <div class="payment-cd-title"><i class="fas fa-credit-card"></i> 正在處理付款...</div>
      <div class="payment-cd-ring-wrap">
        <svg class="payment-cd-ring" viewBox="0 0 120 120">
          <circle class="payment-cd-ring-track" cx="60" cy="60" r="50"></circle>
          <circle id="paymentCdArc" class="payment-cd-ring-arc" cx="60" cy="60" r="50"></circle>
        </svg>
        <div id="paymentCdNumber" class="payment-cd-number">15</div>
      </div>
      <button id="paymentCdCancelBtn" class="payment-cd-cancel" type="button">取消付款</button>
    </div>

    <!-- 失敗 -->
    <div id="paymentCdFailed" class="payment-cd-section hidden">
      <div class="payment-cd-fail-icon"><i class="fas fa-times-circle"></i></div>
      <div class="payment-cd-fail-title">付款失敗</div>
      <div class="payment-cd-help-text">需要協助嗎？</div>
      <button id="paymentCdAssistBtn" class="payment-cd-assist-btn" type="button">
        <i class="fas fa-user-tie"></i> 人員協助付款
      </button>
      <button id="paymentCdBackBtn" class="payment-cd-back-link" type="button">← 返回付款方式選擇</button>
    </div>

    <!-- 通知 / 協助回覆 -->
    <div id="paymentCdNotified" class="payment-cd-section hidden">
      <div class="payment-cd-notify-icon"><i class="fas fa-bell"></i></div>
      <div id="paymentCdNotifyMsg" class="payment-cd-notify-msg">已通知店員，請稍候</div>
      <div class="payment-cd-notify-sub">店員將盡快前來協助您</div>
    </div>

  </div>
```

- [ ] **Step 2: 在 ui.js element map 註冊新元素**

在 `ui` 物件中 `kioskCancelOrderBtn: ...,` 之後新增：

```javascript
  paymentCdBackdrop: document.getElementById('paymentCountdownBackdrop'),
  paymentCdModal: document.getElementById('paymentCountdownModal'),
  paymentCdCounting: document.getElementById('paymentCdCounting'),
  paymentCdFailed: document.getElementById('paymentCdFailed'),
  paymentCdNotified: document.getElementById('paymentCdNotified'),
  paymentCdArc: document.getElementById('paymentCdArc'),
  paymentCdNumber: document.getElementById('paymentCdNumber'),
  paymentCdCancelBtn: document.getElementById('paymentCdCancelBtn'),
  paymentCdAssistBtn: document.getElementById('paymentCdAssistBtn'),
  paymentCdBackBtn: document.getElementById('paymentCdBackBtn'),
  paymentCdNotifyMsg: document.getElementById('paymentCdNotifyMsg'),
```

- [ ] **Step 3: 語法驗證**

Run: `node --check /home/oliver/Project_2026/UI_API/frontend/shared/ui.js`
Expected: 無輸出（成功）

- [ ] **Step 4: Commit**

```bash
git add UI_API/frontend/pos/index.html UI_API/frontend/shared/ui.js
git commit -m "feat(pos): add payment countdown modal markup"
```

---

### Task 6: 付款倒數 Modal — CSS

**Files:**
- Modify: `UI_API/frontend/shared/styles.css`（檔案末尾新增）

- [ ] **Step 1: 在 styles.css 末尾新增 modal 樣式**

```css
/* ── 付款倒數 Modal ───────────────────────────────────── */
.payment-cd-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 80;
}
.payment-cd-backdrop.hidden { display: none; }

.payment-cd-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 81;
  background: #fffdf9;
  color: #1f1b18;
  border-radius: 24px;
  padding: clamp(28px, 4vh, 44px);
  width: min(560px, 80vw);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  text-align: center;
}
.payment-cd-modal.hidden { display: none; }

.payment-cd-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: clamp(16px, 2.4vh, 26px);
}
.payment-cd-section.hidden { display: none; }

.payment-cd-title {
  font-size: clamp(24px, 3vw, 34px);
  font-weight: 900;
}

.payment-cd-ring-wrap {
  position: relative;
  width: clamp(160px, 22vw, 220px);
  height: clamp(160px, 22vw, 220px);
}
.payment-cd-ring {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.payment-cd-ring-track {
  fill: none;
  stroke: #ece6dd;
  stroke-width: 8;
}
.payment-cd-ring-arc {
  fill: none;
  stroke: #1db87a;
  stroke-width: 8;
  stroke-linecap: round;
  stroke-dasharray: 314.16;
  stroke-dashoffset: 0;
  transition: stroke-dashoffset 1s linear, stroke 0.4s ease;
}
.payment-cd-number {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: clamp(64px, 9vw, 96px);
  font-weight: 950;
}

.payment-cd-cancel {
  min-height: clamp(48px, 6vh, 62px);
  padding: 0 clamp(28px, 4vw, 44px);
  border: 2px solid #cfc8c1;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.7);
  font-size: clamp(18px, 2.2vw, 26px);
  font-weight: 800;
  cursor: pointer;
}

.payment-cd-fail-icon {
  font-size: clamp(64px, 8vw, 92px);
  color: #e84040;
}
.payment-cd-fail-title {
  font-size: clamp(34px, 4vw, 50px);
  font-weight: 950;
  color: #e84040;
}
.payment-cd-help-text {
  font-size: clamp(22px, 2.6vw, 32px);
  font-weight: 800;
}
.payment-cd-assist-btn {
  min-height: clamp(64px, 8vh, 84px);
  width: min(440px, 70vw);
  border: none;
  border-radius: 16px;
  background: #ffc72c;
  color: #1f1b18;
  font-size: clamp(24px, 2.8vw, 34px);
  font-weight: 950;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.payment-cd-back-link {
  border: none;
  background: none;
  color: #8a7f72;
  font-size: clamp(18px, 2vw, 24px);
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline;
}

.payment-cd-notify-icon {
  font-size: clamp(56px, 7vw, 80px);
  color: #ffc72c;
}
.payment-cd-notify-msg {
  font-size: clamp(26px, 3vw, 38px);
  font-weight: 900;
  line-height: 1.4;
}
.payment-cd-notify-sub {
  font-size: clamp(18px, 2.2vw, 26px);
  color: #8a7f72;
  font-weight: 600;
}
```

- [ ] **Step 2: Commit**

```bash
git add UI_API/frontend/shared/styles.css
git commit -m "feat(pos): add payment countdown modal styles"
```

---

### Task 7: 倒數狀態機 + Emotion 觸發 + 協助語顯示（app.js）

**Files:**
- Modify: `UI_API/frontend/pos/app.js`（module 變數、新函式、改寫 `kioskFastPayBtn` handler、新增按鈕監聽）

**前置確認：** `runtimeSettings`、`sessionId`、`cartManager`、`api`、`ui`、`trackInteractionEvent`、`capturePreEventClip`（從 media.js import）、`isPosMode`、`finishOrder` 均已在 app.js 作用域內可用。`api.analyzeEmotionEvent(sessionId, eventType, blob)` 回傳 `entry` dict（含 `assist_response`）。

- [ ] **Step 1: 新增 module-level 狀態變數**

在 app.js 既有 `let _voiceProcessing = false;` 附近（module 頂層變數區）新增：

```javascript
let _paymentCdTimer = null;       // 倒數 setInterval handle
let _pendingPaymentAssist = '';   // Emotion-LLaMA → Ollama 協助語
let _paymentCdCartIds = [];       // 本次付款的購物車快照
```

- [ ] **Step 2: 新增 modal 開關 + 狀態切換工具函式**

在 app.js 中 `hidePaymentScreen` 函式之後新增：

```javascript
const PAYMENT_CD_TOTAL = 15;        // 倒數總秒數
const PAYMENT_CD_CIRCUMFERENCE = 314.16;  // 2πr, r=50

function _showPaymentCdSection(name) {
  // name: 'counting' | 'failed' | 'notified'
  ui.paymentCdCounting?.classList.toggle('hidden', name !== 'counting');
  ui.paymentCdFailed?.classList.toggle('hidden', name !== 'failed');
  ui.paymentCdNotified?.classList.toggle('hidden', name !== 'notified');
}

function openPaymentCountdown(cartIds) {
  _paymentCdCartIds = cartIds.slice();
  _pendingPaymentAssist = '';
  ui.paymentCdBackdrop?.classList.remove('hidden');
  ui.paymentCdModal?.classList.remove('hidden');
  _showPaymentCdSection('counting');
  _startPaymentCountdown();
}

function closePaymentCountdown() {
  if (_paymentCdTimer) { clearInterval(_paymentCdTimer); _paymentCdTimer = null; }
  ui.paymentCdBackdrop?.classList.add('hidden');
  ui.paymentCdModal?.classList.add('hidden');
  _pendingPaymentAssist = '';
  _paymentCdCartIds = [];
}
```

- [ ] **Step 3: 新增倒數核心邏輯（含 Emotion 觸發）**

接續在上一函式之後新增：

```javascript
function _startPaymentCountdown() {
  if (_paymentCdTimer) clearInterval(_paymentCdTimer);
  let secondsLeft = PAYMENT_CD_TOTAL;

  // clip_sec 計入後觸發：剩餘 = TOTAL - clip_sec
  const clipSec = Number(runtimeSettings.EMOTION_LLAMA_CLIP_SEC) || 2.0;
  const captureAtRemaining = Math.max(1, Math.round(PAYMENT_CD_TOTAL - clipSec));
  let captured = false;

  const updateUI = () => {
    if (ui.paymentCdNumber) ui.paymentCdNumber.textContent = String(secondsLeft);
    if (ui.paymentCdArc) {
      const elapsed = PAYMENT_CD_TOTAL - secondsLeft;
      ui.paymentCdArc.style.strokeDashoffset =
        String(PAYMENT_CD_CIRCUMFERENCE * (elapsed / PAYMENT_CD_TOTAL));
      const color = secondsLeft > 8 ? '#1db87a' : (secondsLeft > 3 ? '#f5871f' : '#e84040');
      ui.paymentCdArc.style.stroke = color;
    }
  };
  updateUI();

  _paymentCdTimer = setInterval(() => {
    secondsLeft -= 1;
    updateUI();

    if (!captured && secondsLeft === captureAtRemaining
        && runtimeSettings.EMOTION_LLAMA_ENABLED
        && runtimeSettings.EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT !== false) {
      captured = true;
      _triggerPaymentEmotionCapture();
    }

    if (secondsLeft <= 0) {
      clearInterval(_paymentCdTimer);
      _paymentCdTimer = null;
      trackInteractionEvent({
        page_id: 'payment_page',
        event_type: 'payment_timeout',
        button_id: 'paymentCountdownModal',
        metadata: { cart_ids: _paymentCdCartIds }
      });
      _showPaymentCdSection('failed');
    }
  }, 1000);
}

function _triggerPaymentEmotionCapture() {
  if (!isPosMode()) return;
  const blob = capturePreEventClip();
  if (!blob) return;
  api.analyzeEmotionEvent(sessionId, 'payment_timeout', blob)
    .then(data => {
      if (data && data.assist_response) _pendingPaymentAssist = data.assist_response;
    })
    .catch(e => console.warn('[payment] emotion capture failed:', e));
}
```

- [ ] **Step 4: 改寫 `kioskFastPayBtn` handler — 改為開啟 modal**

將既有：

```javascript
ui.kioskFastPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  selectedPayment = 'credit-card';
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_attempt',
    button_id: 'kioskFastPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  finishOrder(cartIds, ui.kioskFastPayBtn, kt('checkoutProcessing'));
});
```

改為：

```javascript
ui.kioskFastPayBtn?.addEventListener('click', () => {
  const cartIds = cartManager.getCartIds();
  if (!cartIds.length) return;
  selectedPayment = 'credit-card';
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_countdown_start',
    button_id: 'kioskFastPayBtn',
    metadata: { payment: selectedPayment, fulfillment: selectedFulfillment, cart_ids: cartIds }
  });
  openPaymentCountdown(cartIds);
});
```

- [ ] **Step 5: 新增 modal 內三顆按鈕的監聽**

緊接在上面 handler 之後新增：

```javascript
ui.paymentCdCancelBtn?.addEventListener('click', () => {
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_countdown_cancel',
    button_id: 'paymentCdCancelBtn',
    metadata: {}
  });
  closePaymentCountdown();
});

ui.paymentCdBackBtn?.addEventListener('click', () => {
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_cd_back',
    button_id: 'paymentCdBackBtn',
    metadata: {}
  });
  closePaymentCountdown();
});

ui.paymentCdAssistBtn?.addEventListener('click', () => {
  trackInteractionEvent({
    page_id: 'payment_page',
    event_type: 'payment_staff_requested',
    button_id: 'paymentCdAssistBtn',
    metadata: { has_assist: Boolean(_pendingPaymentAssist) }
  });
  if (ui.paymentCdNotifyMsg) {
    ui.paymentCdNotifyMsg.textContent = _pendingPaymentAssist || '已通知店員，請稍候';
  }
  _showPaymentCdSection('notified');
});
```

- [ ] **Step 6: 語法驗證**

Run: `node --check /home/oliver/Project_2026/UI_API/frontend/pos/app.js`
Expected: 無輸出（成功）

- [ ] **Step 7: Commit**

```bash
git add UI_API/frontend/pos/app.js
git commit -m "feat(pos): payment countdown state machine + emotion assist display"
```

---

### Task 8: 整合驗證（手動）

**Files:** 無（執行驗證）

- [ ] **Step 1: 啟動服務**

```bash
cd UI_API && conda activate emotion_ui && python main.py
```

- [ ] **Step 2: Admin 端確認開關存在且預設開啟**

開啟 `http://127.0.0.1:8001` → Emotion-LLaMA 頁 → 觸發事件區應有「付款倒數逾時分析（預設開啟）」且勾選。

- [ ] **Step 3: POS 端確認友善模式已移除**

開啟 `http://127.0.0.1:8000` → 加入餐點 → 進入購物車 → 結帳去 → 付款畫面底部應**只有**「取消整單訂單」，無「友善模式」。

- [ ] **Step 4: 確認倒數 modal 流程**

點「在此快速結帳」→ 應出現暗背景 + 倒數環從 15 開始遞減、顏色綠→橙→紅。等 15 秒 → 切換「付款失敗 / 需要協助嗎？」+「人員協助付款」按鈕。

- [ ] **Step 5: 確認協助語顯示**

（需 `EMOTION_LLAMA_ENABLED=true` 且 Gradio 服務運行）倒數中觀察 terminal 應出現 `[Emotion] ... payment_timeout` log。點「人員協助付款」→ modal 顯示 Ollama 生成的協助語（若分析未就緒則顯示「已通知店員，請稍候」）。

- [ ] **Step 6: 確認取消與返回**

重新進入 → 倒數中點「取消付款」→ modal 關閉、回付款畫面。再進入 → 逾時後點「返回付款方式選擇」→ modal 關閉、回付款畫面。

---

## Self-Review

**Spec 覆蓋檢查：**
- 移除友善模式 → Task 4 ✓
- 快速結帳改 modal → Task 7 Step 4 ✓
- 暗背景 + 倒數環 15s → Task 5（HTML）+ Task 6（CSS）+ Task 7 Step 3 ✓
- 逾時顯示付款失敗 + 需要協助 + 人員協助按鈕 → Task 5 + Task 7 Step 3/5 ✓
- 人員協助 = 顯示提示訊息（不關閉 modal）→ Task 7 Step 5（切到 notified 狀態，不呼叫 close）✓
- Emotion 整合預設開啟 → Task 1 ✓
- 觸發時機「剩餘 + clip_sec = 15」→ Task 7 Step 3 `captureAtRemaining = TOTAL - clipSec` ✓
- 分析結果 + prompt → Ollama 協助語 → Task 2 ✓
- 回覆放在人員協助付款中 → Task 7 Step 5 `_pendingPaymentAssist` ✓
- Admin 整合 → Task 3 ✓

**Placeholder 掃描：** 無 TBD/TODO，所有 code step 均含完整程式碼。

**型別/命名一致性：**
- `_pendingPaymentAssist`（Task 7 Step 1/3/5）一致
- `assist_response`（後端 Task 2 / 前端 Task 7 Step 3）一致
- `assist_message`（Ollama JSON key，Task 2 system prompt 與 `result.get`）一致
- `EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT`（config / admin / app.js）一致
- ui 元素 `paymentCd*`（ui.js Task 5 / app.js Task 7）一致
