"""Emotion enrichment must never decide whether a Voice Turn can finish.

A kiosk with no camera, a denied camera permission, or an emotion stack that is
down all reach the Voice Turn through the same seam: scheduling the observation
fails. Ordering has to survive every one of them, so the guarantee belongs to
the module that owns the Voice Turn contract rather than to whichever adapter
happens to swallow the error today.
"""

from modules.voice_turn.module import VoiceTurnModule
from modules.voice_turn.sqlite_store import SQLiteVoiceTurnStore

from models.commercial_scope import LEGACY_DEFAULT_SCOPE


class _STT:
    def transcribe(self, **_kwargs):
        return {"text": "我要一份漢堡"}


class _Assistant:
    def assist(self, **_kwargs):
        return {"text": "好的，請在畫面確認。", "order_draft": None, "mentioned_ids": []}


class _Menu:
    def candidates(self, **_kwargs):
        return [{"item_id": "burger", "available": True}]


class _TTS:
    def synthesize(self, **_kwargs):
        return {"audio_ref": "d2F2", "format": "wav"}


class _EffectsWithoutCamera:
    """Stands in for every way emotion capture can be unavailable."""

    def __init__(self):
        self.history_records = 0

    def schedule_observation(self, **_kwargs):
        raise RuntimeError("emotion_media_unavailable")

    def record_history(self, **_kwargs):
        self.history_records += 1


def _run_turn(tmp_path, effects, voice_turn_id):
    module = VoiceTurnModule(
        store=SQLiteVoiceTurnStore(tmp_path / "voice-turn.sqlite3"),
        stt=_STT(),
        assistant=_Assistant(),
        menu=_Menu(),
        tts=_TTS(),
        effects=effects,
    )
    module.accept(
        scope=LEGACY_DEFAULT_SCOPE,
        session_id="session-degraded",
        audio_ref="/tmp/input.webm",
        voice_turn_id=voice_turn_id,
    )
    return module, module.run(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id=voice_turn_id)


def test_voice_turn_completes_when_emotion_observation_is_unavailable(tmp_path):
    effects = _EffectsWithoutCamera()

    module, result = _run_turn(tmp_path, effects, "turn-no-camera")

    assert result["status"] == "completed"
    assert result["playback_status"] == "available"
    assert result["user_text"] == "我要一份漢堡"
    assert result["assistant_text"] == "好的，請在畫面確認。"
    assert effects.history_records == 1, "ordering history must still be recorded"
    terminal = module.replay(scope=LEGACY_DEFAULT_SCOPE, voice_turn_id="turn-no-camera")[-1]
    assert terminal["type"] == "completed"


def test_failed_emotion_observation_leaves_no_trace_in_the_turn(tmp_path):
    """A skipped enrichment is not a Voice Turn failure and must not be reported as one."""
    _, result = _run_turn(tmp_path, _EffectsWithoutCamera(), "turn-no-camera-2")

    assert result["safe_reason"] == ""
    assert result["status"] != "playback_failed"
