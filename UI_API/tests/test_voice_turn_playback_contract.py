import pytest

from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.voice_turn.module import VoiceTurnModule
from modules.voice_turn.sqlite_store import SQLiteVoiceTurnStore

pytestmark = [pytest.mark.contract]


class _STT:
    def transcribe(self, **_kwargs):
        return {"text": "我要一份漢堡"}


class _Assistant:
    def assist(self, **_kwargs):
        return {"text": "好的，請在畫面確認。", "order_draft": None, "mentioned_ids": []}


class _Menu:
    def candidates(self, **_kwargs):
        return [{"item_id": "burger", "available": True}]


class _Effects:
    def schedule_observation(self, **_kwargs):
        return None

    def record_history(self, **_kwargs):
        return None


class _TTS:
    def __init__(self, audio_ref=""):
        self.audio_ref = audio_ref
        self.calls = 0

    def synthesize(self, **_kwargs):
        self.calls += 1
        return {"audio_ref": self.audio_ref, "format": "wav"}


def _module(tmp_path, tts):
    return VoiceTurnModule(
        store=SQLiteVoiceTurnStore(tmp_path / "voice-turn.sqlite3"),
        stt=_STT(),
        assistant=_Assistant(),
        menu=_Menu(),
        tts=tts,
        effects=_Effects(),
    )


def test_voice_turn_requires_tts_after_bounded_retries(tmp_path):
    tts = _TTS()
    module = _module(tmp_path, tts)
    module.accept(
        scope=LEGACY_DEFAULT_SCOPE,
        session_id="session-1",
        audio_ref="/tmp/input.webm",
        voice_turn_id="turn-1",
    )

    assert module.run(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-1")["retryable"] is True
    assert module.run(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-1")["retryable"] is True
    result = module.run(
        scope=LEGACY_DEFAULT_SCOPE,
        voice_turn_id="turn-1",
        retry_budget_exhausted=True,
    )

    assert tts.calls == 3
    assert result["status"] == "playback_failed"
    assert result["playback_status"] == "failed"
    assert result["assistant_text"] == "好的，請在畫面確認。"
    terminal = module.replay(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-1")[-1]
    assert terminal["type"] == "playback_failed"
    assert terminal["terminal"] is True
    assert terminal["payload"]["code"] == "voice_playback_failure"


def test_voice_turn_completes_only_with_tts_audio(tmp_path):
    module = _module(tmp_path, _TTS("d2F2"))
    module.accept(
        scope=LEGACY_DEFAULT_SCOPE,
        session_id="session-2",
        audio_ref="/tmp/input.webm",
        voice_turn_id="turn-2",
    )

    result = module.run(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-2")

    assert result["status"] == "completed"
    assert result["playback_status"] == "available"
    assert result["audio_ref"] == "d2F2"
