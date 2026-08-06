from __future__ import annotations

from typing import Any, Protocol

from models.commercial_scope import CommercialScope


class VoiceTurnError(RuntimeError):
    def __init__(self, code: str, *, details: dict[str, Any] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}


class TransientVoiceTurnError(RuntimeError):
    pass


class VoiceTurnStore(Protocol):
    def create(self, *, scope: CommercialScope, values: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, *, scope: CommercialScope, voice_turn_id: str) -> dict[str, Any]: ...
    def transition(
        self,
        *,
        scope: CommercialScope,
        voice_turn_id: str,
        expected: set[str],
        status: str,
        updates: dict[str, Any],
        event_type: str,
        payload: dict[str, Any],
        terminal: bool = False,
    ) -> dict[str, Any]: ...
    def record_error(self, *, scope: CommercialScope, voice_turn_id: str, reason: str) -> None: ...
    def events(self, *, scope: CommercialScope, voice_turn_id: str, after_sequence: int) -> list[dict[str, Any]]: ...
    def cleanup_terminal_before(self, *, cutoff: str, limit: int) -> int: ...


class STT(Protocol):
    def transcribe(self, *, audio_ref: str, operation_key: str) -> dict[str, Any]: ...


class Assistant(Protocol):
    def assist(
        self,
        *,
        transcript: str,
        candidates: list[dict[str, Any]],
        operation_key: str,
    ) -> dict[str, Any]: ...


class Menu(Protocol):
    def candidates(self, *, scope: CommercialScope, session_id: str, operation_key: str) -> list[dict[str, Any]]: ...


class TTS(Protocol):
    def synthesize(self, *, text: str, operation_key: str) -> dict[str, Any]: ...


class Effects(Protocol):
    def schedule_observation(self, **values: Any) -> None: ...
    def record_history(self, **values: Any) -> None: ...


TERMINAL = {"completed", "transcription_failed", "assistant_failed", "playback_failed"}


class VoiceTurnModule:
    def __init__(
        self, *, store: VoiceTurnStore, stt: STT, assistant: Assistant, menu: Menu, tts: TTS, effects: Effects
    ):
        self._store = store
        self._stt = stt
        self._assistant = assistant
        self._menu = menu
        self._tts = tts
        self._effects = effects

    def accept(
        self,
        *,
        scope: CommercialScope,
        session_id: str,
        audio_ref: str,
        voice_turn_id: str,
    ) -> dict[str, Any]:
        if not str(session_id).strip() or not str(audio_ref).strip() or not str(voice_turn_id).strip():
            raise VoiceTurnError("invalid_voice_turn")
        return self._store.create(
            scope=scope,
            values={
                "voice_turn_id": voice_turn_id,
                "session_id": session_id,
                "audio_ref": audio_ref,
            },
        )

    def replay(
        self,
        *,
        scope: CommercialScope,
        voice_turn_id: str,
        after_sequence: int = 0,
    ) -> list[dict[str, Any]]:
        return self._store.events(
            scope=scope,
            voice_turn_id=voice_turn_id,
            after_sequence=max(0, int(after_sequence)),
        )

    def cleanup_expired(self, *, cutoff: str, limit: int = 500) -> int:
        return self._store.cleanup_terminal_before(cutoff=cutoff, limit=max(1, min(int(limit), 2000)))

    def run(
        self,
        *,
        scope: CommercialScope,
        voice_turn_id: str,
        retry_budget_exhausted: bool = False,
    ) -> dict[str, Any]:
        turn = self._store.get(scope=scope, voice_turn_id=voice_turn_id)
        if turn["status"] in TERMINAL:
            return self._result(turn)

        if turn["status"] in {"accepted", "transcribing"}:
            if turn["status"] == "accepted":
                turn = self._store.transition(
                    scope=scope,
                    voice_turn_id=voice_turn_id,
                    expected={"accepted"},
                    status="transcribing",
                    updates={},
                    event_type="transcribing",
                    payload={},
                )
            try:
                transcript = self._stt.transcribe(
                    audio_ref=turn["audio_ref"],
                    operation_key=f"{voice_turn_id}:transcribe",
                )
                text = str(transcript.get("text") or "").strip()
                if not text:
                    raise VoiceTurnError("no_speech")
            except TransientVoiceTurnError as exc:
                if not retry_budget_exhausted:
                    self._store.record_error(scope=scope, voice_turn_id=voice_turn_id, reason=str(exc)[:200])
                    return {"voice_turn_id": voice_turn_id, "status": "transcribing", "retryable": True}
                return self._fail(
                    scope=scope,
                    voice_turn_id=voice_turn_id,
                    expected={"transcribing"},
                    status="transcription_failed",
                    reason=str(exc),
                )
            except Exception as exc:
                return self._fail(
                    scope=scope,
                    voice_turn_id=voice_turn_id,
                    expected={"transcribing"},
                    status="transcription_failed",
                    reason=str(exc),
                )
            turn = self._store.transition(
                scope=scope,
                voice_turn_id=voice_turn_id,
                expected={"transcribing"},
                status="assisting",
                updates={"transcript": text, "language": "zh"},
                event_type="transcript",
                payload={"user_text": text},
            )
            self._effects.schedule_observation(
                voice_turn_id=voice_turn_id,
                session_id=turn["session_id"],
                transcript=text,
                audio_ref=turn["audio_ref"],
            )

        if turn["status"] == "assisting":
            try:
                candidates = self._menu.candidates(
                    scope=scope,
                    session_id=turn["session_id"],
                    operation_key=f"{voice_turn_id}:candidates",
                )
                assisted = self._assistant.assist(
                    transcript=turn["transcript"],
                    candidates=candidates,
                    operation_key=f"{voice_turn_id}:assist",
                )
                self._validate_draft(assisted.get("order_draft"), candidates)
            except TransientVoiceTurnError as exc:
                if not retry_budget_exhausted:
                    self._store.record_error(scope=scope, voice_turn_id=voice_turn_id, reason=str(exc)[:200])
                    return {"voice_turn_id": voice_turn_id, "status": "assisting", "retryable": True}
                return self._fail(
                    scope=scope,
                    voice_turn_id=voice_turn_id,
                    expected={"assisting"},
                    status="assistant_failed",
                    reason=str(exc),
                )
            except Exception as exc:
                return self._fail(
                    scope=scope,
                    voice_turn_id=voice_turn_id,
                    expected={"assisting"},
                    status="assistant_failed",
                    reason=str(exc),
                )
            turn = self._store.transition(
                scope=scope,
                voice_turn_id=voice_turn_id,
                expected={"assisting"},
                status="synthesizing",
                updates={
                    "assistant_text": str(assisted.get("text") or "").strip(),
                    "order_draft": assisted.get("order_draft"),
                    "mentioned_ids": assisted.get("mentioned_ids") or [],
                },
                event_type="assistant_result",
                payload={
                    "ai_response": str(assisted.get("text") or "").strip(),
                    "order_draft": assisted.get("order_draft"),
                    "mentioned_ids": assisted.get("mentioned_ids") or [],
                },
            )
            self._effects.record_history(
                voice_turn_id=voice_turn_id,
                session_id=turn["session_id"],
                user_text=turn["transcript"],
                assistant_text=turn["assistant_text"],
                mentioned_ids=turn["mentioned_ids"],
            )

        if turn["status"] == "synthesizing":
            try:
                audio = self._tts.synthesize(
                    text=turn["assistant_text"],
                    operation_key=f"{voice_turn_id}:synthesize",
                )
                if not str(audio.get("audio_ref") or "").strip():
                    raise TransientVoiceTurnError("empty_tts_audio")
            except Exception as exc:
                if not retry_budget_exhausted:
                    self._store.record_error(scope=scope, voice_turn_id=voice_turn_id, reason=str(exc)[:200])
                    return {"voice_turn_id": voice_turn_id, "status": "synthesizing", "retryable": True}
                return self._playback_fail(scope=scope, voice_turn_id=voice_turn_id)
            turn = self._store.transition(
                scope=scope,
                voice_turn_id=voice_turn_id,
                expected={"synthesizing"},
                status="completed",
                updates={
                    "audio_ref": "",
                    "tts_audio_ref": str(audio.get("audio_ref") or ""),
                    "tts_format": str(audio.get("format") or ""),
                    "playback_status": "available",
                },
                event_type="completed",
                payload={
                    "status": "success",
                    "playback_status": "available",
                    "playback_message": "",
                    "user_text": turn["transcript"],
                    "ai_response": turn["assistant_text"],
                    "order_draft": turn["order_draft"],
                    "mentioned_ids": turn["mentioned_ids"],
                    "audio_base64": str(audio.get("audio_ref") or ""),
                    "audio_format": str(audio.get("format") or ""),
                },
                terminal=True,
            )
        return self._result(turn)

    def _playback_fail(self, *, scope, voice_turn_id):
        turn = self._store.get(scope=scope, voice_turn_id=voice_turn_id)
        message = "語音播放失敗，文字結果已保留，請重試語音模式。"
        turn = self._store.transition(
            scope=scope,
            voice_turn_id=voice_turn_id,
            expected={"synthesizing"},
            status="playback_failed",
            updates={
                "audio_ref": "",
                "tts_audio_ref": "",
                "tts_format": "",
                "playback_status": "failed",
                "safe_reason": "voice_playback_failure",
            },
            event_type="playback_failed",
            payload={
                "status": "error",
                "code": "voice_playback_failure",
                "playback_status": "failed",
                "playback_message": message,
                "user_text": turn["transcript"],
                "ai_response": turn["assistant_text"],
            },
            terminal=True,
        )
        return self._result(turn)

    def _fail(self, *, scope, voice_turn_id, expected, status, reason):
        turn = self._store.transition(
            scope=scope,
            voice_turn_id=voice_turn_id,
            expected=expected,
            status=status,
            updates={"audio_ref": "", "safe_reason": str(reason or status)[:200]},
            event_type=status,
            payload={"status": "error", "code": status},
            terminal=True,
        )
        return self._result(turn)

    @staticmethod
    def _validate_draft(draft: Any, candidates: list[dict[str, Any]]) -> None:
        if draft is None:
            return
        if not isinstance(draft, dict) or draft.get("requires_confirmation") is not True:
            raise VoiceTurnError("invalid_voice_order_draft")
        available = {str(row.get("item_id") or row.get("id") or "") for row in candidates if row.get("available", True)}
        lines = draft.get("lines")
        if not isinstance(lines, list) or len(lines) > 20:
            raise VoiceTurnError("invalid_voice_order_draft")
        for line in lines:
            if str(line.get("item_id") or "") not in available:
                raise VoiceTurnError("voice_draft_item_not_available")
            quantity = int(line.get("quantity") or 0)
            if quantity < 1 or quantity > 20:
                raise VoiceTurnError("invalid_voice_draft_quantity")

    @staticmethod
    def _result(turn: dict[str, Any]) -> dict[str, Any]:
        if turn["status"] not in TERMINAL:
            return {
                "voice_turn_id": turn["voice_turn_id"],
                "status": turn["status"],
                "retryable": True,
            }
        return {
            "voice_turn_id": turn["voice_turn_id"],
            "status": turn["status"],
            "retryable": False,
            "user_text": turn["transcript"],
            "assistant_text": turn["assistant_text"],
            "order_draft": turn["order_draft"],
            "mentioned_ids": turn["mentioned_ids"],
            "playback_status": turn["playback_status"],
            "audio_ref": turn["tts_audio_ref"],
            "audio_format": turn["tts_format"],
            "safe_reason": turn["safe_reason"],
        }
