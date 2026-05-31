# 語音點餐與 Emotion-LLaMA 策略說明

## 語音點餐（現況）

語音點餐為乾淨的三段式流程：

```
音訊輸入 → Whisper STT → Ollama LLM → Edge TTS
```

**實作位置：** `backend/services/voice_service.py`

**特性：**
- Whisper 做語音轉文字與語言偵測（zh / en）
- Ollama 依菜單白名單回答問題或生成 `cart_actions`
- `coerce_cart_actions()` 強制校正所有 LLM 輸出的品項 ID
- prompt 組裝前有 `# TODO: inject RAG context here` 插槽，未來接 RAG 只改此處
- 語音模型由 `VOICE_ASSIST_MODEL`（預設 `qwen3.5:4b`）控制

**多語言：**
- `multi_lang=true` 時自動偵測語言，選對應 system prompt 和 TTS 語音
- `VOICE_ASSIST_SYSTEM_PROMPT`（中文）、`VOICE_ASSIST_SYSTEM_PROMPT_EN`（英文）

---

## Emotion-LLaMA（目前為 Stub）

Emotion-LLaMA 目前尚未接入，保留預留介面。

**Stub 位置：** `backend/services/emotion_service.py`

```python
async def analyze(session_id: str, media_path: str) -> dict:
    # TODO: Connect to Emotion-LLaMA at config.EMOTION_LLAMA_GRADIO_URL
    return {
        "emotion_label": "未偵測",
        "emotion_score": 0,
        "emotion_available": False,
        "status": "stub",
    }
```

**Endpoint：** `POST /api/emotion/analyze`（接收 `session_id` + `media` 上傳）

**對接方式（未來）：**
1. 確認 Emotion-LLaMA 服務在 `config.EMOTION_LLAMA_GRADIO_URL`（預設 `http://127.0.0.1:7889`）已啟動
2. 替換 `emotion_service.py` 的 stub 實作，呼叫 Gradio API
3. 回傳格式維持：`{session_id, emotion_label, emotion_score, emotion_available, status}`

**啟動 Emotion-LLaMA（可選）：**
```bash
cd Emotion-LLaMA && conda activate emotion_ollama
python app_EmotionLlamaClient.py --cfg-path eval_configs/demo.yaml --port 7889
```

---

## 設計原則

- Emotion-LLaMA 不直接決定介入動作，只作為輔助證據
- 介入決策由 `barrier_state_service` 基於 POS 事件計數 + 語音關鍵字判斷，與情緒分析解耦
- Stub 狀態下系統完整可用，不依賴 Emotion-LLaMA 服務
