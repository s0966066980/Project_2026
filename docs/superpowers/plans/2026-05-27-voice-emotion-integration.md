# Voice × Emotion-LLaMA 整合實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復語音音量誤判、讓每次語音模式都同步執行 Emotion-LLaMA 分析並將結果注入 AI 回應，精簡 Admin 端 AI 設定頁。

**Architecture:** 語音錄音改為 video/webm（同含音訊軌），後端 `/api/ask` 並行執行 Whisper STT 與 Emotion-LLaMA，情緒結果注入 LLM prompt 並回傳前端顯示。音量門檻從 `-42 dB` 降為 `-58 dB` 以符合 WebRTC 壓縮後的實際音量範圍。

**Tech Stack:** Python 3 asyncio / FastAPI / Vanilla JS / Whisper / Emotion-LLaMA Gradio

---

## 檔案異動對照

| 檔案 | 異動 |
|---|---|
| `UI_API/config.py` | `WHISPER_LOW_AUDIO_DB` 值修正；新增 `EMOTION_LLAMA_ENABLED_FOR_VOICE` |
| `UI_API/routes/voice_routes.py` | `audio` → `media` 參數；傳入 `emotion_semaphore` |
| `UI_API/services/voice_assist_service.py` | `media_path`；並行 Emotion；回傳情緒欄位 |
| `UI_API/static/app.js` | 改用 `createVideoRecorder`；移除快照呼叫；顯示情緒卡片 |
| `UI_API/index.html` | Admin AI 設定 tab 精簡；新增音量門檻輸入 |

---

## Task 1: config.py — 修正音量門檻，新增語音情緒開關

**Files:**
- Modify: `UI_API/config.py`

- [ ] **Step 1: 定位並修改 `WHISPER_LOW_AUDIO_DB`**

在 `config.py` 的 `DEFAULT_SETTINGS` 字典中找到這一行（約第 136 行）：

```python
"WHISPER_LOW_AUDIO_DB": -42,
```

改為：

```python
"WHISPER_LOW_AUDIO_DB": -58,
```

- [ ] **Step 2: 新增 `EMOTION_LLAMA_ENABLED_FOR_VOICE`**

在同一 `DEFAULT_SETTINGS` 字典中，緊接在 `"EMOTION_LOW_AUDIO_DB": -45,` 這行後面加入：

```python
"EMOTION_LLAMA_ENABLED_FOR_VOICE": True,
```

- [ ] **Step 3: 語法檢查**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile config.py
echo "OK"
```

Expected: `OK`（無輸出即通過）

- [ ] **Step 4: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/config.py
git commit -m "fix: 音量門檻 -42→-58 dB；新增 EMOTION_LLAMA_ENABLED_FOR_VOICE 設定"
```

---

## Task 2: voice_routes.py — 接收 media 欄位，傳入 emotion_semaphore

**Files:**
- Modify: `UI_API/routes/voice_routes.py`

- [ ] **Step 1: 修改 endpoint 參數簽章**

將整個 `process_voice_assist` 函式的參數列修改如下（`audio` → `media`，新增 `emotion_semaphore` 傳遞）：

```python
@router.post("/ask")
async def process_voice_assist(
    session_id: str = Form(...),
    media: UploadFile = File(...),          # 原為 audio，現接受 video/webm（含音訊+影像軌）
    multi_lang: str = Form(default="true"),
):
    temp_media_path = None
    try:
        suffix = os.path.splitext(media.filename or ".webm")[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_media_path = tmp.name
        media_bytes = await media.read()
        await asyncio.to_thread(write_binary_file, temp_media_path, media_bytes)

        # Emotion context injected if available from current session
        emotion_structured = (deps.get("emotion_cache") or {}).get(session_id, {}).get("emotion_structured")

        return await voice_assist_service.handle_voice_assist(
            session_id=session_id,
            media_path=temp_media_path,
            multi_lang=multi_lang.lower() == "true",
            ollama_semaphore=deps["ollama_semaphore"],
            emotion_semaphore=deps["emotion_semaphore"],
            emotion_structured=emotion_structured,
        )
    except Exception as e:
        print(f"❌ voice_assist 錯誤: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        if temp_media_path and os.path.exists(temp_media_path):
            os.remove(temp_media_path)
```

- [ ] **Step 2: 語法檢查**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile routes/voice_routes.py
echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/routes/voice_routes.py
git commit -m "feat: voice route 接收 media 欄位，注入 emotion_semaphore"
```

---

## Task 3: voice_assist_service.py — 並行 Whisper + Emotion-LLaMA

**Files:**
- Modify: `UI_API/services/voice_assist_service.py`

- [ ] **Step 1: 修改函式簽章**

將檔案頂部 import 區塊加入（若尚未有）：

```python
import asyncio

import ai_services
import config
import database
from repositories import menu_repository, session_repository
from services import recommendation_service
from services import query_router_service
```

將 `handle_voice_assist` 函式簽章改為：

```python
async def handle_voice_assist(
    session_id: str,
    media_path: str,                     # 原 audio_path，接受 video/webm
    multi_lang: bool,
    ollama_semaphore,
    emotion_semaphore=None,              # 新增：用於並行 Emotion-LLaMA
    emotion_structured: dict | None = None,
) -> dict:
    """
    主入口：STT → Emotion-LLaMA（並行）→ 意圖路由 → LLM 問答 or 直接點餐。
    media_path: 可為 audio/webm 或 video/webm（含影像軌時同步執行 Emotion-LLaMA）。
    """
```

- [ ] **Step 2: 加入並行 Whisper + Emotion-LLaMA 邏輯**

在函式開頭，原本 `stt_result = await ai_services.async_safe_transcribe_with_language(audio_path)` 的地方，替換為以下並行邏輯（注意：把 `audio_path` 改為 `media_path`）：

```python
    loop = asyncio.get_running_loop()

    # 探測媒體類型：有影像軌才執行 Emotion-LLaMA
    probe = await ai_services.async_probe_media(media_path)
    has_video = probe.get("has_video", False)
    emotion_enabled = bool(config.get("EMOTION_LLAMA_ENABLED_FOR_VOICE", True))

    # 並行執行 Whisper STT 與 Emotion-LLaMA（若有影像軌且功能開啟）
    async def _run_emotion():
        if not has_video or not emotion_enabled or emotion_semaphore is None:
            return {}
        async with emotion_semaphore:
            return await ai_services.async_get_emotion_from_llama(media_path)

    stt_task = asyncio.create_task(
        ai_services.async_safe_transcribe_with_language(media_path)
    )
    emotion_task = asyncio.create_task(_run_emotion())

    stt_result, fresh_emotion = await asyncio.gather(stt_task, emotion_task)
```

- [ ] **Step 3: 合併情緒資料並更新 emotion_hint 邏輯**

在上一步的 `stt_result, fresh_emotion = await asyncio.gather(...)` 之後、`user_text = ...` 之前，加入：

```python
    # 優先使用本次語音的新鮮情緒推論，否則退回到 session 快取
    live_emotion = fresh_emotion if fresh_emotion.get("emotion_raw") else {}
    effective_emotion = live_emotion or emotion_structured or {}
```

並在後續 `emotion_hint` 邏輯中（搜尋 `if emotion_structured and not emotion_structured.get("no_person"):`），改為使用 `effective_emotion`：

```python
    # 加入 Emotion-LLaMA 證據（優先使用本次新鮮推論，退回到快取）
    emotion_hint = ""
    if effective_emotion and not effective_emotion.get("no_person"):
        label = (
            effective_emotion.get("emotion_label")
            or effective_emotion.get("emotion_display")
            or effective_emotion.get("emotion_raw")
            or ""
        )
        evidence = effective_emotion.get("emotion_evidence") or ""
        if label and "未執行" not in label and "未偵測" not in label:
            emotion_hint = f"【情緒分析】顧客情緒：{label}。{evidence}\n\n"
```

- [ ] **Step 4: 在所有回傳值中附帶情緒欄位**

本服務共有多個 `return` 分支（`direct_order`、`menu_question`、通用 LLM、fallback）。在**每個** `return` 字典中加入以下三個欄位：

```python
"emotion_structured": effective_emotion or {},
"person_check": live_emotion.get("person_check") or {},
"media_signals": live_emotion.get("media_signals") or {},
```

範例（`direct_order` 分支）：

```python
            return {
                "status": "success",
                "mode": "direct_order",
                "user_text": user_text,
                "ai_response": ai_response,
                "audio_base64": audio_base64,
                "cart_actions": cart_actions,
                "mentioned_ids": [],
                "detected_lang": detected_lang,
                "trigger_recommend": False,
                "emotion_structured": effective_emotion or {},
                "person_check": live_emotion.get("person_check") or {},
                "media_signals": live_emotion.get("media_signals") or {},
            }
```

對 `menu_question`、通用 LLM 成功分支、`error` fallback 分支同樣加入這三行。

- [ ] **Step 5: 語法檢查**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile services/voice_assist_service.py
echo "OK"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/services/voice_assist_service.py
git commit -m "feat: 語音助理並行 Whisper+Emotion-LLaMA，回傳情緒欄位"
```

---

## Task 4: app.js — 改用錄影、移除快照、顯示情緒卡片

**Files:**
- Modify: `UI_API/static/app.js`

#### Step 4-1: setupAskRecorder 改用 createVideoRecorder

- [ ] **Step 1: 修改 setupAskRecorder 函式**

找到 `function setupAskRecorder()` 區塊（約第 1819 行），**完整替換**該函式為：

```javascript
function setupAskRecorder() {
  if (isAdminMode()) return;
  if (askRecorder) return; // 避免重複設定
  if (!stream || !stream.getAudioTracks().length) return;

  // 改用 video recorder：同步捕捉音訊+影像，供後端 Whisper + Emotion-LLaMA 並行使用
  askRecorder = createVideoRecorder(stream);
  let chunks = [];
  askRecorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
  askRecorder.onstop = async () => {
    const blob = new Blob(chunks, { type: 'video/webm' });
    const durationMs = askRecordingStartedAt ? Date.now() - askRecordingStartedAt : 0;
    askRecordingStartedAt = 0;
    chunks = [];
    if (blob.size < 1500 || durationMs < 650) {
      hideVoiceAssistOverlay();
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'audio_too_short', duration_ms: durationMs, bytes: blob.size }
      });
      const _tooShort = document.getElementById('voiceAssistBtnText');
      if (_tooShort) _tooShort.textContent = kt('holdVoiceOrder');
      showVoiceAssistMessage(kt('voiceTooShort'));
      autoVoiceInFlight = false;
      return;
    }

    const _btnText = document.getElementById('voiceAssistBtnText');
    if (_btnText) _btnText.textContent = kt('aiThinking');
    showVoiceAssistOverlay('thinking');
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('media', blob, 'voice_ask.webm');   // 改為 media，對應後端新參數名
    fd.append('multi_lang', String(getFeatures().multiLang));
    try {
      const data = await api.ask(fd);
      if (ui.kioskPaymentScreen && !ui.kioskPaymentScreen.classList.contains('hidden')) {
        hideVoiceAssistOverlay();
        autoVoiceInFlight = false;
        return;
      }
      if (data.status === 'success') {
        lastVoiceText = data.user_text || lastVoiceText;
        if (data.audio_base64) playVoice(data.audio_base64);
        showVoiceBubble(data);

        // 更新本次語音的情緒分析結果
        if (data.emotion_structured && Object.keys(data.emotion_structured).length) {
          lastEmotionStructured = data.emotion_structured;
          lastMediaSignals = data.media_signals || data.emotion_structured?.media_signals || lastMediaSignals || {};
          showEmotionCard(data.emotion_structured);
        }
        if (data.person_check) updateEmotionDetectionOverlay(data.person_check);

        // 累積 session 情緒記錄，結帳時批次寫 RAG
        if (lastEmotionStructured) {
          sessionEmotionLog.push({
            ts: new Date().toISOString(),
            emotion_label: lastEmotionStructured.emotion_label || lastEmotionStructured.emotion_display || '',
            emotion_evidence: lastEmotionStructured.emotion_evidence || '',
            user_text: data.user_text || '',
            ai_response: data.ai_response || '',
          });
        }
        const appliedOrders = cartManager.applyCartActions(data.cart_actions || []);
        if (appliedOrders.length) {
          trackInteractionEvent({
            event_type: 'cart_edit',
            button_id: 'askBtn',
            cart_edit_count: appliedOrders.length,
            metadata: { source: 'voice_assist', items: appliedOrders }
          });
          showPushNotice(kt('addedToCart').replace('{items}', appliedOrders.join('、')));
        }

        if (data.trigger_recommend && getFeatures().recommend) {
          setTimeout(async () => {
            await fetchAndDisplayRecommend();
          }, Number(perfValue('RECOMMEND_AFTER_ASK_DELAY_MS')) || 1200);
        }
        if (data.mentioned_ids) data.mentioned_ids.forEach(id => sessionPushedIds.add(id));
      } else {
        console.debug('[voice assistant skipped]', data.message || data.status);
        showVoiceAssistMessage(
          data.ai_response || data.message || kt('voiceOrderFailed'),
          data.detected_lang || kioskLang
        );
        if (data.audio_base64) playVoice(data.audio_base64);
      }
    } catch (err) {
      trackInteractionEvent({
        event_type: 'voice_assist_failed',
        button_id: 'voiceAssistBtn',
        metadata: { reason: 'api_error' }
      });
      showVoiceBubble({
        detected_lang: 'zh',
        dialogue: { zh: { user_text: '', ai_response: kt('networkFailed') } }
      });
    }
    const _doneText = document.getElementById('voiceAssistBtnText');
    if (_doneText) _doneText.textContent = kt('holdVoiceOrder');
    hideVoiceAssistOverlay();
    autoVoiceInFlight = false;
  };
}
```

#### Step 4-2: 移除 startAskRecording 中的快照呼叫

- [ ] **Step 2: 移除 captureEmotionSnapshotForVoice() 呼叫**

在 `startAskRecording` 函式中找到這一行（約第 1960 行）：

```javascript
    captureEmotionSnapshotForVoice();
```

**刪除**這一行。（`captureEmotionSnapshotForVoice` 函式本體保留，不刪除。）

#### Step 4-3: JS 語法檢查

- [ ] **Step 3: 語法檢查**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js
echo "OK"
```

Expected: `OK`（無報錯）

- [ ] **Step 4: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js
git commit -m "feat: 語音改用錄影模式，整合情緒卡片顯示；移除獨立快照呼叫"
```

---

## Task 5: index.html — Admin AI 設定 tab 精簡

**Files:**
- Modify: `UI_API/index.html`

- [ ] **Step 1: 移除 RAG 狀態顯示區塊**

找到以下區塊（約第 627–634 行）並**整段刪除**：

```html
        <!-- RAG Status Display -->
        <div class="mb-4 p-4 rounded-xl border border-gray-700 bg-[#18201d]">
          <h3 class="text-lg font-bold mb-2" style="color:var(--text)">RAG 檢索狀態</h3>
          <div id="ragStatusContainer" class="text-sm font-mono whitespace-pre-wrap text-gray-300">
            載入中...
          </div>
          <button type="button" onclick="loadRagStatus()" class="mt-3 px-4 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-white transition-colors">重新整理狀態</button>
        </div>
```

- [ ] **Step 2: 精簡 RAG 模組區塊**

找到 `<!-- RAG Status Display -->` 刪除後緊接著的 `<div class="rounded-2xl p-4 space-y-4" style="background:var(--surface2)...">` 區塊（大約是 636–697 行的整個 RAG 調參大區塊），**整段替換**為以下精簡版（只保留品質控制，移除所有內部調參）：

```html
        <div class="rounded-2xl p-4 space-y-3" style="background:var(--surface2);border:1.5px solid var(--border)">
          <div>
            <h3 class="font-bold text-sm" style="color:var(--text)">RAG 答案品質控制</h3>
            <span class="text-orange-400 mt-1 block text-xs"><i class="fas fa-exclamation-triangle"></i> 建議開啟嚴格來源限制，防止 LLM 自行發揮；文件不足時系統會拒答。</span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm" style="color:var(--text)">
            <label class="flex items-center gap-2 text-orange-300"><input type="checkbox" id="inp-rag-strict-grounding"> 嚴格來源限制</label>
            <label class="flex items-center gap-2 text-orange-300"><input type="checkbox" id="inp-rag-answer-verification"> LLM 答案驗證</label>
            <label class="flex items-center gap-2 text-orange-300"><input type="checkbox" id="inp-rag-fail-closed"> 評估失敗時拒答</label>
          </div>
        </div>
```

- [ ] **Step 3: 移除 Gemini 冷卻秒數欄位**

找到以下區塊（`inp-gemini-cooldown`）並刪除它（整個 `<div>` 容器，約第 602–606 行）：

```html
          <div>
            <label class="block font-semibold mb-1.5 text-sm" style="color:var(--text)">Gemini 冷卻秒數</label>
            <input type="number" id="inp-gemini-cooldown" min="10" max="600" step="5" class="w-full p-2.5 rounded-xl text-sm outline-none" style="border:1.5px solid var(--border);background:var(--surface2)" value="60">
            <p class="text-xs mt-1" style="color:var(--text2)">若 Gemini 錯誤回傳 retryDelay，會優先使用官方建議秒數。</p>
          </div>
```

- [ ] **Step 4: 新增語音音量門檻輸入**

在 `inp-emotion-interval` 所在的 grid 區塊（約第 698–712 行）的 `</div>` 之前，**新增**一個欄位（讓 grid 變成 4 欄）：

找到這個 grid 開頭標籤（原本是 3 欄）：

```html
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
```

改為 4 欄：

```html
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
```

然後在 `inp-recommend-interval` 的 `</div>` 後面（grid 閉合前）加入：

```html
          <div>
            <label class="block font-semibold mb-1.5 text-sm" style="color:var(--text)">語音音量門檻 (dB)</label>
            <input type="number" id="inp-whisper-low-db" min="-80" max="-20" step="1" class="w-full p-2.5 rounded-xl text-sm outline-none" style="border:1.5px solid var(--border);background:var(--surface2)">
            <p class="text-xs mt-1" style="color:var(--text2)">低於此音量略過 Whisper 辨識。預設 -58 dB。</p>
          </div>
```

- [ ] **Step 5: 語法檢查（HTML 結構）**

```bash
python3 -c "
from html.parser import HTMLParser
class V(HTMLParser): pass
v = V()
with open('UI_API/index.html', encoding='utf-8') as f:
    v.feed(f.read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/index.html
git commit -m "refactor: admin AI設定tab精簡，移除RAG內部調參，新增語音音量門檻輸入"
```

---

## Task 6: app.js — loadSettings / saveSettings 同步更新

**Files:**
- Modify: `UI_API/static/app.js`

- [ ] **Step 1: loadSettings 新增讀取 WHISPER_LOW_AUDIO_DB**

在 `loadSettings` 函式中，找到以下這行（約第 2698–2700 行）：

```javascript
    document.getElementById('inp-emotion-interval').value = fullSettings.EMOTION_PING_INTERVAL_SEC || 15;
    document.getElementById('inp-emotion-record-ms').value = fullSettings.EMOTION_RECORD_MS || 900;
    document.getElementById('inp-recommend-interval').value = fullSettings.RECOMMEND_INTERVAL_SEC || 30;
```

在這三行後面加入：

```javascript
    document.getElementById('inp-whisper-low-db').value = fullSettings.WHISPER_LOW_AUDIO_DB ?? -58;
```

- [ ] **Step 2: saveSettings 移除已刪除欄位的讀取，新增音量門檻存取**

在 `saveSettings` 函式中，找到 `fullSettings.GEMINI_COOLDOWN_SEC = ...` 這行（約第 2725 行）：

```javascript
  fullSettings.GEMINI_COOLDOWN_SEC = parseInt(document.getElementById('inp-gemini-cooldown').value || '60', 10);
```

**刪除**這一行。

然後找到以下區塊（約 2740–2749 行的 `fullSettings.RAG_CONFIG = { ... }` 賦值）：

```javascript
  fullSettings.RAG_CONFIG = {
    ...
    min_keyword_overlap: parseInt(document.getElementById('inp-rag-min-overlap').value || '1', 10),
    max_answer_chars: parseInt(document.getElementById('inp-rag-max-chars').value || '420', 10),
    top_k_vector: parseInt(document.getElementById('inp-rag-top-k-vector').value || '10', 10),
    top_k_keyword: parseInt(document.getElementById('inp-rag-top-k-keyword').value || '10', 10),
    top_k_final: parseInt(document.getElementById('inp-rag-top-k-final').value || '5', 10),
    context_max_chars: parseInt(document.getElementById('inp-rag-context-max').value || '2600', 10),
    embedding_provider: document.getElementById('inp-rag-embedding-provider').value || 'ollama',
    embedding_model: document.getElementById('inp-rag-embedding-model').value.trim() || 'nomic-embed-text',
    reranker_model: document.getElementById('inp-rag-reranker-model').value.trim() || 'cross-encoder/ms-marco-MiniLM-L-6-v2'
  };
```

**替換**為（移除已刪除 HTML 元素的讀取，保留品質控制 checkbox，以及固定預設值確保後端不丟失設定）：

```javascript
  const _existingRag = fullSettings.RAG_CONFIG || {};
  fullSettings.RAG_CONFIG = {
    ..._existingRag,                     // 保留後端目前值（已移除 UI 的調參不被清空）
    strict_grounding: document.getElementById('inp-rag-strict-grounding')?.checked ?? _existingRag.strict_grounding ?? false,
    answer_verification: document.getElementById('inp-rag-answer-verification')?.checked ?? _existingRag.answer_verification ?? false,
    fail_closed: document.getElementById('inp-rag-fail-closed')?.checked ?? _existingRag.fail_closed ?? false,
  };
```

然後找到（約第 2750–2752 行）：

```javascript
  fullSettings.EMOTION_PING_INTERVAL_SEC = parseFloat(document.getElementById('inp-emotion-interval').value || '15');
  fullSettings.EMOTION_RECORD_MS = parseInt(document.getElementById('inp-emotion-record-ms').value || '900', 10);
  fullSettings.RECOMMEND_INTERVAL_SEC = parseFloat(document.getElementById('inp-recommend-interval').value || '30');
```

在這三行後面加入：

```javascript
  fullSettings.WHISPER_LOW_AUDIO_DB = parseFloat(document.getElementById('inp-whisper-low-db')?.value || '-58');
```

- [ ] **Step 3: 語法檢查**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js
echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/oliver/Project_2026
git add UI_API/static/app.js
git commit -m "feat: loadSettings/saveSettings 同步音量門檻欄位，精簡RAG調參存取"
```

---

## Task 7: 整合驗證

- [ ] **Step 1: Python 全模組語法檢查**

```bash
cd /home/oliver/Project_2026/UI_API
python3 -m py_compile config.py routes/voice_routes.py services/voice_assist_service.py ai_services.py
echo "all OK"
```

Expected: `all OK`

- [ ] **Step 2: JS 語法檢查**

```bash
node --check /home/oliver/Project_2026/UI_API/static/app.js
node --check /home/oliver/Project_2026/UI_API/static/api.js
echo "all OK"
```

Expected: `all OK`

- [ ] **Step 3: 啟動服務確認兩個 port 正常（需 conda 環境）**

```bash
# 在另一個 terminal 啟動服務
cd /home/oliver/Project_2026/UI_API && python main.py &
sleep 5
curl -s http://127.0.0.1:8000/api/settings | python3 -c "import sys,json; d=json.load(sys.stdin); print('8000 OK, WHISPER_LOW_AUDIO_DB=', d.get('WHISPER_LOW_AUDIO_DB','N/A'))"
curl -s http://127.0.0.1:8001/api/settings | python3 -c "import sys,json; d=json.load(sys.stdin); print('8001 OK')"
```

Expected output:
```
8000 OK, WHISPER_LOW_AUDIO_DB= -58
8001 OK
```

- [ ] **Step 4: 最終 commit（若有微調）**

```bash
cd /home/oliver/Project_2026
git add -A
git commit -m "chore: 整合驗證完成"
```
