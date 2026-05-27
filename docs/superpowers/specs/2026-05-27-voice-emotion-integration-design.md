# 語音模式 × Emotion-LLaMA 整合設計

**日期**: 2026-05-27  
**範圍**: 音量門檻修正、Emotion-LLaMA cache 問題修復、語音模式全面整合情緒分析、Admin 端精簡

---

## 背景與問題

| 問題 | 根因 |
|---|---|
| ⚠️ 音量過低略過 Whisper | `WHISPER_LOW_AUDIO_DB: -42 dB` 門檻過嚴；瀏覽器 WebRTC + WebM 壓縮後音量常低於此值 |
| Emotion-LLaMA 前幾次後停止動作 | `EMOTION_MIN_GAP_SEC: 12`：語音模式觸發的 1 秒預捕捉快照在 12 秒 cache gate 內直接返回快取，不執行新推論 |
| 語音回應未整合情緒 | `/api/ask` 只收 audio；Emotion 快照為獨立非同步，兩者解耦，無法保證每次語音都有對應情緒分析 |

---

## 設計決策

### 1. 音量門檻修正

**檔案**: `UI_API/config.py`

```python
# 修改前
"WHISPER_LOW_AUDIO_DB": -42,

# 修改後
"WHISPER_LOW_AUDIO_DB": -58,
```

**理由**: 瀏覽器 WebRTC AGC/雜訊消除 + WebM Opus 壓縮後，正常說話音量 RMS 常落在 -45 ~ -55 dBFS，-42 門檻會錯誤過濾真實語音。-58 仍可排除真正的靜音片段（< -60 dBFS）。

---

### 2. 語音模式同步錄影 + Emotion-LLaMA 整合

#### 前端 (app.js)

**改動點一：`setupAskRecorder()`**

```
變更前：createAudioRecorder(stream)  → 只捕捉音訊
變更後：createVideoRecorder(stream)  → 同步捕捉音訊 + 影像
```

- `blob` 類型改為 `video/webm`
- `fd.append('audio', blob)` → `fd.append('media', blob, 'voice_ask.webm')`

**改動點二：`startAskRecording()`**

- 移除 `captureEmotionSnapshotForVoice()` 的呼叫（情緒分析已整合進 `/api/ask`）

**改動點三：`onstop` callback**

- 收到回應若有 `emotion_structured` → 呼叫 `showEmotionCard(data.emotion_structured)` 並更新 `lastEmotionStructured`
- 收到回應若有 `person_check` → 呼叫 `updateEmotionDetectionOverlay(data.person_check)`

#### 後端 voice_routes.py

```python
# 變更前
async def process_voice_assist(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    multi_lang: str = Form(default="true"),
):

# 變更後
async def process_voice_assist(
    session_id: str = Form(...),
    media: UploadFile = File(...),   # video/webm，同時含音訊與影像軌道
    multi_lang: str = Form(default="true"),
):
```

- 傳給 service 的參數名稱由 `audio_path` 改為 `media_path`
- emotion_cache 注入保留（兼容週期情緒模式仍可提供背景情緒）

#### 後端 voice_assist_service.py

```python
async def handle_voice_assist(
    session_id: str,
    media_path: str,          # 原 audio_path，現接受 video/webm
    multi_lang: bool,
    ollama_semaphore,
    emotion_structured: dict | None = None,
):
```

**新並行流程**（關鍵改動）：

```python
# Step 1: probe 判斷是否有影像軌道
probe = await async_probe_media(media_path)
has_video = probe.get("has_video", False)

# Step 2: 並行執行 Whisper + Emotion-LLaMA
stt_task = asyncio.create_task(
    ai_services.async_safe_transcribe_with_language(media_path)
)
emotion_task = asyncio.create_task(
    ai_services.async_get_emotion_from_llama(media_path)
) if has_video and config.get("EMOTION_LLAMA_ENABLED_FOR_VOICE", True) else None

stt_result = await stt_task
emotion_data = await emotion_task if emotion_task else {}

# Step 3: 融合情緒 hint 進 LLM prompt（沿用現有邏輯，但優先使用新鮮推論結果）
```

**Semaphore 處理**：`voice_assist_service` 目前無 `emotion_semaphore`。  
`voice_routes.py` 須從 `deps["emotion_semaphore"]` 取得後傳入 service，或在 route 層以 `async with emotion_semaphore:` 包裹 service 呼叫。選擇**在 service 接收 semaphore 參數**，與現有 `ollama_semaphore` 模式一致。

**回應新增欄位**：

```json
{
  "status": "success",
  "user_text": "...",
  "ai_response": "...",
  "audio_base64": "...",
  "cart_actions": [],
  "emotion_structured": { ... },   // 新增：本次語音的情緒分析
  "person_check": { ... },         // 新增：人物偵測結果
  "media_signals": { ... }         // 新增：音量/動作訊號
}
```

---

### 3. Admin 端精簡

**目標**：只保留專利核心參數，移除 RAG 內部調參與非必要 UI 元素。

#### 移除項目（AI 設定 tab）

| 移除元素 | 理由 |
|---|---|
| RAG 狀態顯示區塊 | 開發除錯工具，非專利展示項目 |
| `top_k_vector / top_k_keyword / top_k_final` | RAG 內部調參，非專利核心 |
| `Context 字數上限` | 同上 |
| `Embedding Provider / Ollama Embedding Model / Reranker Model` | RAG 實作細節 |
| `Gemini 冷卻秒數` | 次要設定 |
| `Multi-Query / Hybrid Search / Reranker / Context Compress / Answer Eval` checkboxes | RAG 實作細節 |

#### 新增項目（AI 設定 tab）

| 新增元素 | 說明 |
|---|---|
| `WHISPER_LOW_AUDIO_DB` 音量門檻 | 方便展示時調整敏感度 |

#### 保留項目（AI 設定 tab）

- 問答服務來源（Ollama / Gemini）
- 本地 Ollama 模型選擇
- 推論溫度 (Temperature)
- LLM 輸出上限
- 情緒間隔秒 / 偵測影片長度 / 推播間隔秒
- TTS 快取
- Emotion LLaMA Prompt
- 推播 Prompt（Ollama 推薦）
- 語音問答 Prompt（中/英）
- 嚴格來源限制 / LLM 答案驗證 / 評估失敗時拒答（保留，與答案品質相關）
- RAG 筆數（`top_k_final` 的簡化版）

---

## 新設定鍵

| 鍵名 | 預設值 | 說明 |
|---|---|---|
| `EMOTION_LLAMA_ENABLED_FOR_VOICE` | `True` | 語音模式是否強制觸發 Emotion-LLaMA |

---

## 不變動項目

- `captureEmotionSnapshotForVoice()` 函式本體保留（供其他呼叫點使用），只移除 `startAskRecording` 中的呼叫
- 週期情緒 loop（`startEmotionLoop`）邏輯不變
- `EMOTION_MIN_GAP_SEC` 設定不變（週期模式仍適用）
- checkout 流程不變
- RAG 文本管理 tab 保留（移除的只是 AI 設定 tab 中的 RAG 參數）
- `barrier_state_service` / `intervention_service` 不變

---

## 檔案異動清單

| 檔案 | 異動類型 |
|---|---|
| `UI_API/config.py` | 修改 `WHISPER_LOW_AUDIO_DB`，新增 `EMOTION_LLAMA_ENABLED_FOR_VOICE` |
| `UI_API/routes/voice_routes.py` | `audio` → `media` 參數 |
| `UI_API/services/voice_assist_service.py` | 加入並行 Emotion-LLaMA 呼叫，回傳情緒欄位 |
| `UI_API/static/app.js` | 改錄影、移除快照呼叫、顯示情緒卡片 |
| `UI_API/index.html` | Admin AI 設定 tab 精簡 |
