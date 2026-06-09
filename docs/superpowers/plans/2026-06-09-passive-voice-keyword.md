# Passive Voice Keyword Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 開始點餐後自動啟動被動語音監聽，偵測到 admin 設定的關鍵詞（如「找不到」「在哪裡」）且 transcript 中含有菜單品項名稱時，顯示猶豫彈跳視窗並帶入該品項；無法比對到品項時不顯示。

**Architecture:** 使用瀏覽器原生 Web Speech API（`SpeechRecognition`，`continuous: true`）持續監聽；偵測到關鍵詞時對 `menuData` 做子字串比對取出品項，直接呼叫現有 `renderChoiceHesitationItem` + 彈窗顯示，不需後端呼叫。主動語音模式（`startAskRecording`）啟動時暫停，`onstop` finally 後恢復；系統回到首頁或點餐完成時停止。

**Tech Stack:** Web Speech API（`window.SpeechRecognition` / `webkitSpeechRecognition`）、現有 FastAPI config 系統、Vanilla JS

---

## Files

| 動作 | 路徑 | 說明 |
|---|---|---|
| Modify | `UI_API/config.py` | 新增 `PASSIVE_VOICE_KEYWORDS` DEFAULT_SETTINGS + PUBLIC_SETTINGS_KEYS |
| Modify | `UI_API/frontend/pos/app.js` | 新增被動監聽模組；在 startSystem / stopSystem / startAskRecording / onstop finally 掛接 |
| Modify | `UI_API/frontend/admin/admin.html` | 在功能設定右欄新增關鍵詞 textarea |
| Modify | `UI_API/frontend/admin/admin.js` | `loadSettings` / `saveSettings` 讀寫 `PASSIVE_VOICE_KEYWORDS` |

---

## Task 1：config.py — 新增 PASSIVE_VOICE_KEYWORDS

**Files:**
- Modify: `UI_API/config.py`

- [ ] **Step 1：在 DEFAULT_SETTINGS 的 `CHOICE_HESITATION_IDLE_SEC` 原位置（已刪）後加入設定**

在 `DEFAULT_SETTINGS` 的 `AI_PUSH_REFRESH_SEC` 附近加入：

```python
    "PASSIVE_VOICE_KEYWORDS": ["找不到", "在哪裡", "哪邊有", "哪裡有", "哪裡可以"],
```

完整插入位置範例（在 `"AI_PUSH_REFRESH_SEC"` 這行之後）：

```python
    "AI_PUSH_REFRESH_SEC": 15,              # 推播欄刷新間隔（秒）
    "PASSIVE_VOICE_KEYWORDS": ["找不到", "在哪裡", "哪邊有", "哪裡有", "哪裡可以"],
```

- [ ] **Step 2：加入 PUBLIC_SETTINGS_KEYS**

```python
PUBLIC_SETTINGS_KEYS = {
    ...
    "AI_PUSH_REFRESH_SEC",
    "PAYMENT_EMOTION_CLIP_SEC",
    "PASSIVE_VOICE_KEYWORDS",      # ← 新增
}
```

- [ ] **Step 3：語法確認**

```bash
cd UI_API && python3 -m py_compile config.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 4：Commit**

```bash
git add UI_API/config.py
git commit -m "feat(passive-voice): add PASSIVE_VOICE_KEYWORDS setting"
```

---

## Task 2：app.js — 被動監聽模組

**Files:**
- Modify: `UI_API/frontend/pos/app.js`

### 2-A 新增模組變數與核心函式

- [ ] **Step 1：在 `let currentChoiceHesitationItem` 附近（module-level vars 區）加入變數**

```js
let _passiveRecognition = null;
let _passiveListening = false;     // 是否應維持監聽（系統層級開關）
let _passiveLastTriggerAt = 0;
const PASSIVE_TRIGGER_COOLDOWN_MS = 10000;
```

- [ ] **Step 2：在 app.js 末尾（`// =========================================================` 的最後一個 section 之後，`connectRealtime(...)` 之前）新增被動監聽 section**

```js
// =========================================================
// 被動語音監聽（Web Speech API）
// =========================================================

function startPassiveListener() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  if (_passiveListening) return;
  _passiveListening = true;
  _passiveRecognition = new SR();
  _passiveRecognition.continuous = true;
  _passiveRecognition.interimResults = true;
  _passiveRecognition.lang = 'zh-TW';

  _passiveRecognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      _handlePassiveTranscript(event.results[i][0].transcript || '');
    }
  };

  _passiveRecognition.onend = () => {
    // Web Speech API 會在靜音後自動 end；若應繼續就重啟
    if (_passiveListening && !_isVoiceActive()) {
      setTimeout(() => {
        if (_passiveListening && _passiveRecognition) {
          try { _passiveRecognition.start(); } catch {}
        }
      }, 500);
    }
  };

  try { _passiveRecognition.start(); } catch {}
}

function stopPassiveListener() {
  _passiveListening = false;
  if (_passiveRecognition) {
    try { _passiveRecognition.abort(); } catch {}
    _passiveRecognition = null;
  }
}

function _pausePassiveListener() {
  if (_passiveRecognition) {
    try { _passiveRecognition.abort(); } catch {}
  }
}

function _resumePassiveListener() {
  if (!_passiveListening || !_passiveRecognition) return;
  setTimeout(() => {
    if (_passiveListening && _passiveRecognition) {
      try { _passiveRecognition.start(); } catch {}
    }
  }, 400);
}

function _handlePassiveTranscript(transcript) {
  if (!transcript || !isPosActive() || orderCompleted) return;
  if (_isVoiceActive()) return;
  if (Date.now() - _passiveLastTriggerAt < PASSIVE_TRIGGER_COOLDOWN_MS) return;

  const keywords = Array.isArray(runtimeSettings.PASSIVE_VOICE_KEYWORDS)
    ? runtimeSettings.PASSIVE_VOICE_KEYWORDS
    : [];
  if (!keywords.some(kw => kw && transcript.includes(kw))) return;

  // 在 transcript 中尋找菜單品項名稱（子字串比對）
  const item = menuData.find(m => m && m.name && transcript.includes(m.name));
  if (!item) return;

  _passiveLastTriggerAt = Date.now();
  _showHesitationForItem(item);
}

function _showHesitationForItem(item) {
  if (isChoiceHesitationVisible()) return;
  if (!isSystemRunning || orderCompleted || !isPosActive()) return;
  currentChoiceHesitationItem = item;
  renderChoiceHesitationItem(item);
  getChoiceHesitationModal()?.classList.remove('hidden');
}
```

- [ ] **Step 3：語法確認**

```bash
node --check UI_API/frontend/pos/app.js && echo "OK"
```

Expected: `OK`

### 2-B 掛接系統生命週期

- [ ] **Step 4：在 startSystem（`isSystemRunning = true` 之後）加入 startPassiveListener()**

找到這個區塊：
```js
    isSystemRunning = true;
    lastCartAddAt = Date.now();
    startPageDwellWatcher();
```

改為：
```js
    isSystemRunning = true;
    lastCartAddAt = Date.now();
    startPageDwellWatcher();
    startPassiveListener();
```

- [ ] **Step 5：在 kioskHomeBtn click handler（回到首頁）加入 stopPassiveListener()**

找到：
```js
  isSystemRunning = false;
  orderCompleted = false;
  totalClickCount = 0;
  clearPOSFloatingUI();
  stopChoiceHesitationTimer();
```

改為：
```js
  isSystemRunning = false;
  orderCompleted = false;
  totalClickCount = 0;
  clearPOSFloatingUI();
  stopChoiceHesitationTimer();
  stopPassiveListener();
```

- [ ] **Step 6：在 startAskRecording() 的 `askRecorder.start()` 之前暫停被動監聽**

找到：
```js
    askRecordingStartedAt = Date.now();
    askRecorder.start();
```

改為：
```js
    _pausePassiveListener();
    askRecordingStartedAt = Date.now();
    askRecorder.start();
```

- [ ] **Step 7：在 onstop 的 `finally` 區塊恢復被動監聽**

找到：
```js
    } finally {
      _voiceProcessing = false;
    }
```

改為：
```js
    } finally {
      _voiceProcessing = false;
      _resumePassiveListener();
    }
```

- [ ] **Step 8：語法確認**

```bash
node --check UI_API/frontend/pos/app.js && echo "OK"
```

Expected: `OK`

- [ ] **Step 9：Commit**

```bash
git add UI_API/frontend/pos/app.js
git commit -m "feat(passive-voice): add passive SpeechRecognition listener with keyword + menu matching"
```

---

## Task 3：admin.html — 關鍵詞設定 textarea

**Files:**
- Modify: `UI_API/frontend/admin/admin.html`

- [ ] **Step 1：在功能設定右欄（`<!-- ── 右欄：System Prompts ── -->` 附近）找到 AI 推播相關 section，在其後加入被動語音關鍵詞 section**

找到 admin.html 中 AI 推播 section 的結束 `</section>`，在其後加入：

```html
<hr style="border:none;border-top:1px solid #edf0f7">

<section>
  <div class="section-title">被動語音監聽關鍵詞</div>
  <div class="setting-row" style="align-items:flex-start">
    <label class="setting-label" style="padding-top:6px">觸發關鍵詞</label>
    <div style="flex:1;display:flex;flex-direction:column;gap:6px">
      <textarea id="inp-passive-keywords" class="setting-input" rows="4"
        style="resize:vertical;font-size:13px;line-height:1.6"
        placeholder="每行一個關鍵詞，例如：&#10;找不到&#10;在哪裡&#10;哪邊有"></textarea>
      <span style="font-size:11px;color:#8494b0">顧客說出關鍵詞且提到菜單品項名稱時，自動顯示猶豫彈窗</span>
    </div>
  </div>
</section>
```

- [ ] **Step 2：確認 HTML 格式正確（無裸露 `<`、`>`）**

用瀏覽器開啟 admin 頁面，或：

```bash
node -e "
const fs = require('fs');
const html = fs.readFileSync('UI_API/frontend/admin/admin.html','utf8');
console.log(html.includes('inp-passive-keywords') ? 'OK' : 'NOT FOUND');
"
```

Expected: `OK`

- [ ] **Step 3：Commit**

```bash
git add UI_API/frontend/admin/admin.html
git commit -m "feat(passive-voice): add keyword textarea in admin settings"
```

---

## Task 4：admin.js — 讀寫 PASSIVE_VOICE_KEYWORDS

**Files:**
- Modify: `UI_API/frontend/admin/admin.js`

**格式約定：** settings.json 儲存 array，admin textarea 顯示每行一個關鍵詞；讀取時 `array.join('\n')`，儲存時 `split('\n').map(s=>s.trim()).filter(Boolean)`。

- [ ] **Step 1：在 `loadSettings()` 的心情 Prompt 讀取之後加入**

找到：
```js
    [1,2,3,4,5].forEach(n => setVal(`inp-mood-ctx-${n}`, s[`MOOD_CONTEXT_${n}`] || ''));
```

在其後加入：
```js
    const kws = Array.isArray(s.PASSIVE_VOICE_KEYWORDS) ? s.PASSIVE_VOICE_KEYWORDS : [];
    setVal('inp-passive-keywords', kws.join('\n'));
```

- [ ] **Step 2：在 `saveSettings()` 的 body 物件中加入**

找到：
```js
      ...Object.fromEntries([1,2,3,4,5].map(n => [`MOOD_CONTEXT_${n}`, val(`inp-mood-ctx-${n}`)])),
```

在其後加入：
```js
      PASSIVE_VOICE_KEYWORDS: (val('inp-passive-keywords') || '')
        .split('\n').map(s => s.trim()).filter(Boolean),
```

- [ ] **Step 3：語法確認**

```bash
node --check UI_API/frontend/admin/admin.js && echo "OK"
```

Expected: `OK`

- [ ] **Step 4：Commit**

```bash
git add UI_API/frontend/admin/admin.js
git commit -m "feat(passive-voice): read/write PASSIVE_VOICE_KEYWORDS in admin settings"
```

---

## Task 5：手動驗證

- [ ] **Step 1：啟動服務**

```bash
cd UI_API && conda activate emotion_ui && python main.py
```

- [ ] **Step 2：Admin 設定關鍵詞**

1. 開啟 `http://127.0.0.1:8001` → 功能設定
2. 在「被動語音監聽關鍵詞」填入：
   ```
   找不到
   在哪裡
   ```
3. 按儲存，確認顯示「✓ 儲存成功」

- [ ] **Step 3：POS 驗證 — 正常觸發**

1. 開啟 `http://127.0.0.1:8000`，點「開始點餐」
2. 瀏覽器請求麥克風權限 → 允許
3. 對著麥克風說：「**大麥克在哪裡**」
4. 預期：猶豫彈跳視窗出現，顯示大麥克的名稱與 `item.description`

- [ ] **Step 4：POS 驗證 — 無品項時不顯示**

1. 說：「**在哪裡**」（只有關鍵詞，無品項名稱）
2. 預期：彈窗不出現

- [ ] **Step 5：POS 驗證 — 與主動語音共存**

1. 按下語音助理按鈕（主動模式）
2. 主動語音正常運作，結束後被動監聽自動恢復
3. 再次說「**大麥克在哪裡**」，彈窗正常出現

- [ ] **Step 6：POS 驗證 — 回首頁停止監聽**

1. 點 logo 回首頁
2. 再次說「**大麥克在哪裡**」，彈窗不出現（系統未啟動）
3. 重新點「開始點餐」，監聽恢復正常

- [ ] **Step 7：Cooldown 確認**

1. 說「**大麥克在哪裡**」觸發彈窗
2. 關閉彈窗，立刻再說一次
3. 預期：10 秒內不再觸發

---

## 注意事項

- **Web Speech API 需要 HTTPS 或 localhost**：kiosk 在 `127.0.0.1` 直接訪問可正常運作；若透過 ngrok 或外部網址需確認 HTTPS
- **瀏覽器支援**：Chrome / Edge 支援；Firefox 不支援 `SpeechRecognition`（kiosk 通常用 Chrome，可忽略）
- **`isChoiceHesitationEligible()` 不在 `_showHesitationForItem` 中使用**：被動觸發不要求購物車為空，兩者為獨立觸發路徑
- **`PASSIVE_VOICE_KEYWORDS` 為陣列**：`config.py` PUBLIC_SETTINGS_KEYS 回傳給 POS 時直接傳 JSON array，`runtimeSettings.PASSIVE_VOICE_KEYWORDS` 即為 JS array
