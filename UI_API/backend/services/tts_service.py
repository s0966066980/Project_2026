"""TTS Provider 抽象介面與實作。

切換方式：config TTS_PROVIDER
  "edge"              — Edge TTS 雲端（預設，需網路，zh-TW 品質最佳）
  "melo"              — MeloTTS 本地函式庫（需另行安裝）
  "openai_compatible" — HTTP API（OpenAI 或本地相容服務）

回傳格式：
  Edge TTS            → MP3 bytes  (audio_format = "mp3")
  MeloTTS             → WAV bytes  (audio_format = "wav")
  OpenAI compatible   → MP3 bytes  (audio_format = "mp3")
"""
import asyncio
import base64
import os
import tempfile
from abc import ABC, abstractmethod

import config


class TTSProvider(ABC):
    audio_format: str = "wav"

    @abstractmethod
    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        """文字 → 音訊 bytes"""

    async def synthesize_base64(self, text: str, lang: str = "zh") -> str:
        """文字 → base64 字串（供 HTTP 傳輸）"""
        if not text:
            return ""
        audio = await self.synthesize(text, lang)
        return base64.b64encode(audio).decode("utf-8") if audio else ""


# ── Edge TTS 雲端實作 ─────────────────────────────────────────────

class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge TTS — 需網路，zh-TW 品質最佳。
    pip install edge-tts
    """
    audio_format = "mp3"

    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        import edge_tts

        voice = (
            config.get("EDGE_TTS_VOICE_EN", "en-US-JennyNeural")
            if lang == "en"
            else config.get("EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")
        )
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp = f.name
        try:
            await communicate.save(tmp)
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


# ── MeloTTS 本地實作 ──────────────────────────────────────────────

class MeloTTSProvider(TTSProvider):
    audio_format = "wav"
    _model = None

    def _init(self):
        if MeloTTSProvider._model is None:
            from melo.api import TTS
            print("載入 MeloTTS (ZH, CPU)...")
            MeloTTSProvider._model = TTS(language="ZH", device="cpu")

    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        self._init()

        def _run() -> bytes:
            speaker_id = MeloTTSProvider._model.hps.data.spk2id["ZH"]
            speed = float(config.get("TTS_SPEED", 1.0))
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp = f.name
            try:
                MeloTTSProvider._model.tts_to_file(text, speaker_id, tmp, speed=speed)
                with open(tmp, "rb") as f:
                    return f.read()
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

        return await asyncio.to_thread(_run)


# ── OpenAI 相容 HTTP API 實作 ─────────────────────────────────────

class OpenAICompatibleTTS(TTSProvider):
    """相容 OpenAI /v1/audio/speech 的任意 HTTP 服務。

    本地相容服務範例：openedai-speech（TTS_API_KEY 可填 "none"）
    雲端：OpenAI API（TTS_API_KEY 填 sk-xxx）
    """
    audio_format = "mp3"

    async def synthesize(self, text: str, lang: str = "zh") -> bytes:
        import httpx

        url = config.get("TTS_API_URL", "https://api.openai.com").rstrip("/")
        api_key = config.get("TTS_API_KEY", "none") or "none"
        model = config.get("TTS_MODEL", "tts-1")
        voice = config.get("TTS_VOICE", "alloy")

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{url}/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "input": text,
                    "voice": voice,
                    "response_format": "mp3",
                },
            )
            r.raise_for_status()
        return r.content


# ── Factory ───────────────────────────────────────────────────────

def get_tts() -> TTSProvider:
    """Config TTS_PROVIDER 決定使用哪個實作。"""
    provider = config.get("TTS_PROVIDER", "edge")
    match provider:
        case "melo":
            return MeloTTSProvider()
        case "openai_compatible":
            return OpenAICompatibleTTS()
        case _:
            return EdgeTTSProvider()  # 預設 edge
