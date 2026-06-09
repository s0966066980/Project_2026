"""STT Provider 抽象介面與實作。

切換方式：config STT_PROVIDER
  "faster_whisper"    — 本地函式庫（預設）
  "openai_compatible" — HTTP API（OpenAI 或本地相容服務）
"""
import asyncio
import threading
from abc import ABC, abstractmethod

import config


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_path: str) -> dict:
        """音訊檔 → {"text": str, "language": "zh"|"en"}"""


# ── FasterWhisper 本地實作 ────────────────────────────────────────

class FasterWhisperSTT(STTProvider):
    _model = None
    _lock = threading.Lock()

    def _init(self):
        if FasterWhisperSTT._model is None:
            from faster_whisper import WhisperModel
            model_size = config.get("STT_MODEL", "small")
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            print(f"載入 faster-whisper ({model_size}, {compute_type}, {device})...")
            try:
                FasterWhisperSTT._model = WhisperModel(
                    model_size,
                    device=device,
                    compute_type=compute_type,
                    num_workers=2,
                )
            except Exception as e:
                print(f"⚠️  GPU 載入失敗（{e}），退回 CPU int8")
                FasterWhisperSTT._model = WhisperModel(
                    model_size,
                    device="cpu",
                    compute_type="int8",
                    num_workers=2,
                )

    async def transcribe(self, audio_path: str, initial_prompt: str | None = None) -> dict:
        self._init()
        language = config.get("STT_LANGUAGE", "zh") or None
        prompt = initial_prompt if initial_prompt is not None else config.get("STT_INITIAL_PROMPT", "")

        def _run():
            with FasterWhisperSTT._lock:
                segments, info = FasterWhisperSTT._model.transcribe(
                    audio_path,
                    language=language,
                    initial_prompt=prompt or None,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300},
                )
            text = "".join(seg.text for seg in segments).strip()
            lang = info.language or "zh"
            return {
                "text": text,
                "language": "zh" if lang.startswith("zh") else "en",
            }

        return await asyncio.to_thread(_run)


# ── OpenAI 相容 HTTP API 實作 ─────────────────────────────────────

class OpenAICompatibleSTT(STTProvider):
    """相容 OpenAI /v1/audio/transcriptions 的任意 HTTP 服務。

    本地相容服務範例：faster-whisper-server（STT_API_KEY 可填 "none"）
    雲端：OpenAI API（STT_API_KEY 填 sk-xxx）
    """

    async def transcribe(self, audio_path: str) -> dict:
        import httpx

        url = config.get("STT_API_URL", "https://api.openai.com").rstrip("/")
        api_key = config.get("STT_API_KEY", "none") or "none"
        language = config.get("STT_LANGUAGE", "zh")
        model = config.get("STT_MODEL", "whisper-1")

        async with httpx.AsyncClient(timeout=float(config.get("STT_HTTP_TIMEOUT_SEC", 30))) as client:
            with open(audio_path, "rb") as f:
                r = await client.post(
                    f"{url}/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("audio.webm", f, "audio/webm")},
                    data={"model": model, "language": language, "response_format": "json"},
                )
            r.raise_for_status()

        data = r.json()
        return {
            "text": (data.get("text") or "").strip(),
            "language": language or "zh",
        }


# ── Factory ───────────────────────────────────────────────────────

def get_stt() -> STTProvider:
    """Config STT_PROVIDER 決定使用哪個實作。"""
    provider = config.get("STT_PROVIDER", "faster_whisper")
    if provider == "openai_compatible":
        return OpenAICompatibleSTT()
    return FasterWhisperSTT()
