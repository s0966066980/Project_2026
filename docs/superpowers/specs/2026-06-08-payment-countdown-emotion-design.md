# 結帳倒數付款 Modal + Emotion-LLaMA 整合設計

**日期：** 2026-06-08  
**範圍：** `frontend/pos/index.html`、`frontend/pos/app.js`、`frontend/shared/styles.css`、`backend/services/emotion_service.py`、`config.py`、`frontend/admin/admin.html`、`frontend/admin/admin.js`

---

## 一、移除「友善模式」

| 位置 | 操作 |
|---|---|
| `index.html` | 刪除 `kiosk-payment-footer` 內的友善模式 `<button>` |
| `config.py` | 刪除 `friendlyMode` i18n key（zh + en） |
| `app.js` | 刪除 `setKioskLanguage()` 中 `friendlyBtn.textContent` 賦值 |
| `styles.css` | `.kiosk-payment-footer` 改為單按鈕佈局（移除 `grid-template-columns: 1fr 1fr`） |

Footer 只保留「取消整單訂單」按鈕。

---

## 二、付款倒數 Modal

### 2.1 HTML 結構

```html
<!-- backdrop（暗色遮罩，z=80） -->
<div id="paymentCountdownBackdrop" class="payment-cd-backdrop hidden"></div>

<!-- modal 本體（z=81） -->
<div id="paymentCountdownModal" class="payment-cd-modal hidden" role="dialog"
     aria-modal="true" aria-label="付款處理中">

  <!-- 計時中狀態 -->
  <div id="paymentCdCounting" class="payment-cd-section">
    <div class="payment-cd-title">
      <i class="fas fa-credit-card"></i> 正在處理付款...
    </div>
    <!-- SVG 圓形倒數環 -->
    <svg class="payment-cd-ring" viewBox="0 0 120 120">
      <circle class="payment-cd-ring-track" cx="60" cy="60" r="50"/>
      <circle id="paymentCdArc" class="payment-cd-ring-arc" cx="60" cy="60" r="50"/>
    </svg>
    <div id="paymentCdNumber" class="payment-cd-number">15</div>
    <button id="paymentCdCancelBtn" class="payment-cd-cancel" type="button">
      取消付款
    </button>
  </div>

  <!-- 失敗狀態（計時結束） -->
  <div id="paymentCdFailed" class="payment-cd-section hidden">
    <div class="payment-cd-fail-icon"><i class="fas fa-times-circle"></i></div>
    <div class="payment-cd-fail-title">付款失敗</div>
    <div class="payment-cd-help-text">需要協助嗎？</div>
    <button id="paymentCdAssistBtn" class="payment-cd-assist-btn" type="button">
      <i class="fas fa-user-tie"></i> 人員協助付款
    </button>
    <button id="paymentCdBackBtn" class="payment-cd-back-link" type="button">
      ← 返回付款方式選擇
    </button>
  </div>

  <!-- 通知／協助回覆狀態 -->
  <div id="paymentCdNotified" class="payment-cd-section hidden">
    <div class="payment-cd-notify-icon"><i class="fas fa-bell"></i></div>
    <div id="paymentCdNotifyMsg" class="payment-cd-notify-msg">
      已通知店員，請稍候
    </div>
    <div class="payment-cd-notify-sub">店員將盡快前來協助您</div>
  </div>

</div>
```

### 2.2 狀態機

```
hidden → counting (點擊「在此快速結帳」)
counting → failed (倒數到 0)
counting → hidden (點「取消付款」→ 回付款畫面)
failed → notified (點「人員協助付款」)
failed → hidden (點「返回付款方式選擇」)
notified → (不自動關閉，使用者可等候店員)
```

### 2.3 倒數邏輯（JS）

```
TOTAL = 15 秒
每秒更新 #paymentCdNumber
SVG arc: stroke-dashoffset 從 0 → CIRCUMFERENCE（314.16）隨時間線性增加
setInterval 1000ms × 15 次 → clearInterval → 切換到 failed 狀態
```

### 2.4 CSS 設計要點

- `payment-cd-backdrop`：`position:fixed; inset:0; background:rgba(0,0,0,0.55); z-index:80`
- `payment-cd-modal`：`position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); z-index:81; background:#fff; border-radius:24px; padding:40px; width:min(560px,80vw)`
- 倒數環：SVG `stroke-dasharray:314; stroke-dashoffset:0→314`，`transition:stroke-dashoffset 1s linear`
- 數字：大字（`clamp(72px,9vw,96px)`），倒數時綠→橙→紅（>8:green, 4-8:orange, <4:red）
- 失敗狀態：紅色圓形圖示，大字「付款失敗」，主 CTA 按鈕（麥當勞黃）
- 通知狀態：bell 圖示、主訊息大字、副字說明

---

## 三、Emotion-LLaMA 整合

### 3.1 新設定 key

```python
# config.py EDITABLE_SETTINGS
"EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT": True,   # 付款倒數觸發分析（預設開啟）
```

加入 `PUBLIC_SETTINGS_KEYS`，讓 POS 可讀取。

### 3.2 前端觸發時機

**觸發時間點**：倒數剩餘時間 = `15 - EMOTION_LLAMA_CLIP_SEC` 秒時觸發

即：`clip_sec` 秒計入倒數後呼叫 `capturePreEventClip()`

```javascript
// 在 setInterval 回呼中
const clipSec = Number(runtimeSettings.EMOTION_LLAMA_CLIP_SEC) || 2.0;
const captureAtRemaining = Math.round(15 - clipSec);  // e.g. 13 with 2s clip

if (secondsLeft === captureAtRemaining
    && runtimeSettings.EMOTION_LLAMA_ENABLED
    && runtimeSettings.EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT) {
  // 背景觸發，不阻擋 UI；分析結果存入 _pendingAssistResponse
  _triggerPaymentEmotionCapture(sessionId);
}
```

`_triggerPaymentEmotionCapture`：
- 呼叫 `api.analyzeEmotionEvent(sessionId, 'payment_timeout', blob)`
- 回應中若有 `assist_response` → 存入 `_pendingAssistResponse`

### 3.3 後端擴充

**`emotion_service.py`** — `analyze_event` 在 `payment_timeout` 事件且情緒提取成功後，新增 Ollama assist 訊息生成：

```python
if (event_type == "payment_timeout"
        and not quality_skipped and not error
        and entry.get("emotion")):
    try:
        assist = await _generate_payment_assist(entry)
        entry["assist_response"] = assist
    except Exception as e:
        print(f"⚠️ Payment assist Ollama 失敗: {e}")
```

**`_generate_payment_assist(entry)`**：

```python
async def _generate_payment_assist(entry: dict) -> str:
    system = (
        "你是麥當勞自助點餐機的智能協助員。"
        "根據顧客情緒分析，生成一句溫暖友善的協助語（繁體中文，20–40 字）。"
        "不要提及分析流程，用自然語氣說話，適合付款遇困難時安慰顧客。"
        '只輸出 JSON：{"assist_message":"..."}'
    )
    user = (
        f"顧客情緒：{entry.get('emotion','')}（強度：{entry.get('intensity','')}）\n"
        f"表情：{entry.get('facial','')}\n"
        f"描述：{entry.get('description','')[:150]}\n"
        "請生成友善協助語。"
    )
    result = await asyncio.to_thread(
        ai_services.ask_ollama, system, user, "PAYMENT_ASSIST",
        config.get("MODEL_NAME", "qwen3.5:4b"), 80
    )
    return str(result.get("assist_message") or "")
```

`emotion_routes.py` 的 `analyze_emotion_event` 回傳 `entry`，前端從 `data.assist_response` 取值。

### 3.4 時序保證

```
t=0      點「在此快速結帳」→ 倒數開始（15s）
t=2      剩 13s → 觸發 analyzeEmotionEvent（fire-and-forget，存 promise）
t=2~12   Gradio 分析 + Ollama 情緒提取 + Ollama assist 生成（~5–10s）
         → promise resolve → _pendingAssistResponse = data.assist_response
t=15     倒數歸零 → 切換 failed 狀態
t≥15     使用者點「人員協助付款」→ 讀 _pendingAssistResponse（此時通常已就緒）
```

觸發在 `t=2` 給後端 13 秒處理時間，使用者最快也要 `t=15` 後才點按鈕，
因此 assist 回覆通常已抵達。若仍未抵達（分析慢/失敗），fallback 顯示預設文字。

前端用 module-level `let _pendingPaymentAssist = '';`：
- 觸發前清空：`_pendingPaymentAssist = '';`
- promise resolve：`_pendingPaymentAssist = data.assist_response || '';`
- modal 關閉時清空（避免殘留到下次）

### 3.5 通知狀態顯示

點「人員協助付款」時：

```javascript
const msg = _pendingPaymentAssist || '已通知店員，請稍候';
document.getElementById('paymentCdNotifyMsg').textContent = msg;
// 切換到 notified 狀態
```

若 `_pendingAssistResponse` 尚未到達（分析中），顯示預設文字；若已到達則顯示 Ollama 回覆。

### 3.6 Admin UI 新增

在 Emotion-LLaMA 設定卡片「觸發事件」區塊新增：

```html
<div style="display:flex;align-items:center;gap:12px">
  <label style="min-width:200px;font-size:13px;color:var(--text2)">
    付款倒數逾時分析（預設開啟）
  </label>
  <input type="checkbox" id="inp-emotion-event-payment-timeout">
</div>
```

`admin.js` `loadEmotionSettings` / `saveEmotionSettings` 讀寫 `EMOTION_LLAMA_EVENT_PAYMENT_TIMEOUT`。

`EVENT_TYPE_LABELS` 新增：

```python
# emotion_service.py
EVENT_TYPE_LABELS = {
    "tutorial_popup": "如何點餐彈跳視窗",
    "payment_timeout": "付款逾時協助",
}
```

---

## 四、互動事件追蹤

| 事件 | `event_type` | `button_id` |
|---|---|---|
| 開啟 modal | `payment_countdown_start` | `kioskFastPayBtn` |
| 取消付款 | `payment_countdown_cancel` | `paymentCdCancelBtn` |
| 計時歸零 | `payment_timeout` | — |
| 點人員協助 | `payment_staff_requested` | `paymentCdAssistBtn` |
| 返回付款 | `payment_cd_back` | `paymentCdBackBtn` |

---

## 五、不在本次範圍

- 實際 NFC/卡片感應整合
- 自動通知後台 WebSocket（人員協助按鈕僅顯示文字，不推送）
- Modal 期間語音點餐的暫停/恢復邏輯
