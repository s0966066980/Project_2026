from uuid import uuid4

from modules.voice_turn import (
    SQLiteVoiceTurnStore,
    TransientVoiceTurnError,
    VoiceTurnModule,
)

from models.commercial_scope import CommercialScope


class ScriptedSTT:
    def __init__(self):
        self.calls = 0
        self.error = None

    def transcribe(self, *, audio_ref, operation_key):
        self.calls += 1
        if self.error:
            raise self.error
        return {"text": "我要一份薯條"}


class ScriptedAssistant:
    def __init__(self):
        self.calls = 0
        self.error = None

    def assist(self, *, transcript, candidates, operation_key):
        self.calls += 1
        if self.error:
            raise self.error
        return {
            "text": "請確認一份薯條。",
            "mentioned_ids": ["fries"],
            "order_draft": {
                "draft_id": "draft-1",
                "lines": [{"item_id": "fries", "quantity": 1}],
                "requires_confirmation": True,
            },
        }


class ScriptedMenu:
    def candidates(self, *, scope, session_id, operation_key):
        return [{"item_id": "fries", "name": "薯條", "available": True}]


class ScriptedTTS:
    def __init__(self):
        self.calls = 0
        self.error = None

    def synthesize(self, *, text, operation_key):
        self.calls += 1
        if self.error:
            raise self.error
        return {"audio_ref": "audio://turn-1", "format": "mp3"}


class RecordingEffects:
    def __init__(self):
        self.observations = []
        self.history = []

    def schedule_observation(self, **values):
        self.observations.append(values)

    def record_history(self, **values):
        self.history.append(values)


def test_event_terminal_parameter_is_database_portable_boolean():
    class Result:
        @staticmethod
        def fetchone():
            return {"next": 1}

    class Connection:
        def __init__(self):
            self.calls = []

        def execute(self, statement, parameters=()):
            self.calls.append((statement, parameters))
            return Result()

    connection = Connection()
    SQLiteVoiceTurnStore._append_event(
        connection,
        "tenant",
        "store",
        "turn",
        "accepted",
        {},
        False,
        "2026-07-28T00:00:00+00:00",
    )

    assert type(connection.calls[-1][1][6]) is bool


def build_module(database, stt, assistant, tts, effects):
    return VoiceTurnModule(
        store=SQLiteVoiceTurnStore(database),
        stt=stt,
        assistant=assistant,
        menu=ScriptedMenu(),
        tts=tts,
        effects=effects,
    )


def test_voice_turn_completes_with_durable_monotonic_replay(tmp_path):
    scope = CommercialScope(uuid4(), uuid4())
    stt, assistant, tts, effects = ScriptedSTT(), ScriptedAssistant(), ScriptedTTS(), RecordingEffects()
    voice = build_module(tmp_path / "voice.sqlite3", stt, assistant, tts, effects)
    accepted = voice.accept(
        scope=scope,
        session_id="session-1",
        audio_ref="upload://audio-1",
        voice_turn_id="turn-1",
    )

    result = voice.run(scope=scope, voice_turn_id=accepted["voice_turn_id"])

    assert result["status"] == "completed"
    assert result["order_draft"]["lines"] == [{"item_id": "fries", "quantity": 1}]
    assert result["playback_status"] == "available"
    events = voice.replay(scope=scope, voice_turn_id="turn-1", after_sequence=2)
    assert [event["sequence"] for event in events] == list(
        range(events[0]["sequence"], events[-1]["sequence"] + 1)
    )
    assert events[-1]["terminal"] is True
    assert len(effects.observations) == 1
    assert len(effects.history) == 1


def test_restart_resumes_after_transcription_without_repeating_stt(tmp_path):
    database = tmp_path / "voice.sqlite3"
    scope = CommercialScope(uuid4(), uuid4())
    stt, assistant, tts, effects = ScriptedSTT(), ScriptedAssistant(), ScriptedTTS(), RecordingEffects()
    assistant.error = TransientVoiceTurnError("assistant unavailable")
    voice = build_module(database, stt, assistant, tts, effects)
    voice.accept(scope=scope, session_id="session-1", audio_ref="upload://audio-1", voice_turn_id="turn-1")

    retry = voice.run(scope=scope, voice_turn_id="turn-1", retry_budget_exhausted=False)
    assert retry == {"voice_turn_id": "turn-1", "status": "assisting", "retryable": True}

    assistant.error = None
    reopened = build_module(database, stt, assistant, tts, effects)
    completed = reopened.run(scope=scope, voice_turn_id="turn-1")
    assert completed["status"] == "completed"
    assert stt.calls == 1
    assert assistant.calls == 2


def test_stt_exhaustion_records_exactly_one_terminal_event(tmp_path):
    scope = CommercialScope(uuid4(), uuid4())
    stt, assistant, tts, effects = ScriptedSTT(), ScriptedAssistant(), ScriptedTTS(), RecordingEffects()
    stt.error = TransientVoiceTurnError("stt unavailable")
    voice = build_module(tmp_path / "voice.sqlite3", stt, assistant, tts, effects)
    voice.accept(scope=scope, session_id="session-1", audio_ref="upload://audio-1", voice_turn_id="turn-1")

    failed = voice.run(scope=scope, voice_turn_id="turn-1", retry_budget_exhausted=True)
    replayed = voice.run(scope=scope, voice_turn_id="turn-1", retry_budget_exhausted=True)

    assert failed["status"] == "transcription_failed"
    assert replayed == failed
    events = voice.replay(scope=scope, voice_turn_id="turn-1")
    assert sum(event["terminal"] for event in events) == 1
    assert assistant.calls == 0


def test_tts_failure_completes_with_text_and_degraded_playback(tmp_path):
    scope = CommercialScope(uuid4(), uuid4())
    stt, assistant, tts, effects = ScriptedSTT(), ScriptedAssistant(), ScriptedTTS(), RecordingEffects()
    tts.error = RuntimeError("tts unavailable")
    voice = build_module(tmp_path / "voice.sqlite3", stt, assistant, tts, effects)
    voice.accept(scope=scope, session_id="session-1", audio_ref="upload://audio-1", voice_turn_id="turn-1")

    result = voice.run(scope=scope, voice_turn_id="turn-1", retry_budget_exhausted=True)

    assert result["status"] == "completed"
    assert result["assistant_text"] == "請確認一份薯條。"
    assert result["playback_status"] == "degraded"
    completed = voice.replay(scope=scope, voice_turn_id="turn-1", after_sequence=0)[-1]
    assert completed["payload"]["playback_message"] == "文字結果已保留，但語音播放暫時不可用。"
    assert len(effects.history) == 1
