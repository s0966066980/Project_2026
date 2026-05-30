"""Emotion-LLaMA 情緒分析 stub — 預留對接介面。"""


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
