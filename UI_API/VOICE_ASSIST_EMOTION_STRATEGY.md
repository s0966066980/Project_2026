# 語音點餐與 Emotion-LLaMA 策略說明

## 語音點餐（現況）

語音點餐為乾淨的三段式流程：

```
音訊輸入 → Whisper STT → Ollama LLM → Edge TTS
```

**實作位置：** `backend/services/voice_service.py`

**特性：**
- STT 支援 faster-whisper（本地）或 openai-compatible（雲端）
- Ollama 依菜單白名單回答問題或生成 `cart_actions`
- `coerce_cart_actions()` 強制校正所有 LLM 輸出的品項 ID
- prompt 組裝前有 `# TODO: inject RAG context here` 插槽，未來接 RAG 只改此處
- 語音模型由 `VOICE_ASSIST_MODEL`（預設 `qwen3.5:4b`）控制

**多語言：**
- `multi_lang=true` 時自動偵測語言，選對應 system prompt 和 TTS 語音
- `VOICE_ASSIST_SYSTEM_PROMPT`（中文）、`VOICE_ASSIST_SYSTEM_PROMPT_EN`（英文）

**Emotion-LLaMA 注入（可選）：**
- 若 `EMOTION_LLAMA_AFFECT_VOICE=true`，`voice_service` 在組 prompt 前讀取 `emotion_service.get_voice_emotion_cache(session_id)`
- 快取命中時在 `user_prompt` 前加入 `【顧客情緒參考】` 區塊（情緒、強度、表情、語調）
- 同時在 system_prompt 後加一句：「若有顧客情緒參考，請據此調整語氣，但不要直接提及你在分析情緒。」

---

## Emotion-LLaMA（事件驅動，可選）

Emotion-LLaMA 採事件觸發方式運作，**非持續分析**。

### 觸發流程

```
前端：「如何點餐」彈跳視窗（或其他事件）觸發
  → _triggerEmotionCapture('tutorial_popup')
    → capturePreEventClip()（截取 rolling buffer 最近 N 秒）
    → POST /api/emotion/analyze_event（非阻擋 fire-and-forget）
      → emotion_service.analyze_event()
        → _call_gradio(video_path, question, skip_quality_check)
        → emotion_log_repository.append_log(entry)
        → 更新 _voice_cache[session_id]
        → （可選）asyncio.create_task(_trigger_barrier_update())
```

### Rolling Buffer

- `media.js` 的 `startRollingBuffer(stream, clipSec)` 在「開始點餐」時啟動
- 每 500ms 產生一個 chunk，維持固定長度（`clipSec + 緩衝`）的環形 buffer
- `capturePreEventClip()` 在事件發生時快照 buffer，回傳 `Blob`

### 啟動條件

- `runtimeSettings.EMOTION_LLAMA_ENABLED === true`（`PUBLIC_SETTINGS_KEYS` 中，POS 可讀）
- `runtimeSettings.EMOTION_LLAMA_CLIP_SEC`（截片秒數，也在 Public Settings）
- Emotion-LLaMA 服務需在 `config.EMOTION_LLAMA_GRADIO_URL`（預設 `http://127.0.0.1:7889`）

### 啟動 Emotion-LLaMA 服務

```bash
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

### 後台設定（Admin → Emotion-LLaMA）

| 設定 | 說明 |
|------|------|
| `EMOTION_LLAMA_ENABLED` | 啟用事件分析 |
| `EMOTION_LLAMA_CLIP_SEC` | 截片秒數（預設 2.0） |
| `EMOTION_LLAMA_QUALITY_CHECK` | 啟用品質快篩（`skip_quality_check=false`） |
| `EMOTION_LLAMA_AFFECT_VOICE` | 分析結果注入下一輪語音 prompt |
| `EMOTION_LLAMA_AFFECT_BARRIER` | 分析結果觸發 barrier pipeline |
| `EMOTION_LLAMA_PROMPT` | 分析 prompt 模板（`{speech_text}` 為佔位） |

---

## 設計原則

- Emotion-LLaMA 不直接決定介入動作，只作為輔助證據
- 介入決策由 `barrier_state_service` 基於 POS 事件計數 + 語音關鍵字判斷，與情緒分析解耦
- 所有 Emotion 功能均可透過 `EMOTION_LLAMA_ENABLED=false` 完全關閉，不影響系統其他功能
- `analyze()` 保留 stub 格式維持向下相容，避免舊呼叫端報錯
