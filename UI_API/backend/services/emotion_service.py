"""Emotion-LLaMA 情緒分析 stub — 預留對接介面。

相關設定（learning_data/settings.json）：
  EMOTION_LLAMA_ENABLED_FOR_VOICE  (bool) — 是否啟用語音模式情緒分析
  EMOTION_LLAMA_PROMPT             (str)  — 分析提問模板，含 {speech_text}
  EMOTION_LLAMA_VOICE_TIMEOUT_SEC  (float)— 呼叫逾時秒數
"""
import config


def is_enabled() -> bool:
    """回傳 Emotion-LLaMA 是否設定為啟用。"""
    return bool(config.get("EMOTION_LLAMA_ENABLED_FOR_VOICE", True))


async def analyze(session_id: str, media_path: str) -> dict:
    # TODO: Connect to Emotion-LLaMA at config.EMOTION_LLAMA_GRADIO_URL
    # Replace this stub when Emotion-LLaMA service is ready.
    return {
        "session_id": session_id,
        "emotion_label": "未偵測",
        "emotion_score": 0,
        "emotion_available": False,
        "status": "stub",
    }
