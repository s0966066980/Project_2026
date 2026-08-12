"""Published advisory-only Emotion Diagnostics surface."""

from __future__ import annotations

from typing import Any

from capabilities.emotion.contracts import EmotionCapabilityError, EmotionObservation


def model_profiles() -> list[dict[str, Any]]:
    from services import emotion_service

    return emotion_service.model_profiles()


def default_prompt() -> str:
    from services import emotion_service

    return str(emotion_service.default_prompt())


def default_profile() -> str:
    from services import emotion_service

    return str(emotion_service.MODEL_PROFILE)


def readiness() -> dict[str, Any]:
    from services import emotion_service

    profile = (emotion_service.model_profiles() or [{}])[0]
    ready = bool(profile.get("ready"))
    return {"status": "ready" if ready else "unavailable", "ready": ready, "provider": profile}


async def analyze_event(*, session_id: str, media_path: str, event_type: str) -> dict[str, Any]:
    from services import emotion_service

    return await emotion_service.analyze_event(
        session_id=session_id,
        media_path=media_path,
        event_type=event_type,
    )


async def analyze_live_diagnostic(media_path: str, *, model_profile: str, prompt: str) -> dict[str, Any]:
    from services import emotion_service

    return await emotion_service.analyze_live_diagnostic(
        media_path,
        model_profile=model_profile,
        prompt=prompt,
    )


def list_records(limit: int = 200) -> list[dict[str, Any]]:
    from repositories import emotion_log_repository

    return emotion_log_repository.get_records(limit)


def clear_records() -> int:
    from repositories import emotion_log_repository

    return emotion_log_repository.clear_records()


__all__ = [
    "EmotionCapabilityError",
    "EmotionObservation",
    "analyze_event",
    "analyze_live_diagnostic",
    "clear_records",
    "default_profile",
    "default_prompt",
    "list_records",
    "model_profiles",
    "readiness",
]
