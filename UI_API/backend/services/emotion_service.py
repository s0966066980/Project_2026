"""Single-pass R1-Omni emotion analysis without intervention authority."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import config
from models.multimodal_evidence import MultimodalEvidenceRequest
from repositories import emotion_log_repository
from services.multimodal_evidence_gateway import collect_evidence, configured_provider_status

logger = logging.getLogger(__name__)

MODEL_PROFILE = "r1_omni"
CAPTURE_MODES = {"off", "periodic_ordering", "voice_only"}
EMOTIONS = {"neutral", "happy", "angry", "frustrated", "anxious", "confused", "undetermined"}
INTENSITIES = {"low", "medium", "high", "undetermined"}
EVENT_LABELS = {
    "voice_mode_ended": "語音模式",
    "ordering_periodic": "點餐中定期分析",
    "admin_live_test": "即時影音情緒測試",
}


def capture_mode() -> str:
    value = str(config.get("EMOTION_CAPTURE_MODE", "off") or "off")
    return value if value in CAPTURE_MODES else "off"


def default_prompt() -> str:
    return str(config.get("EMOTION_PROMPT", "") or config.DEFAULT_SETTINGS["EMOTION_PROMPT"]).strip()


def model_profiles() -> list[dict]:
    status = configured_provider_status()
    return [
        {
            "id": MODEL_PROFILE,
            "label": "R1-Omni",
            "ready": status.get("status") == "ready",
            "status": status.get("status", "unavailable"),
            "capabilities": status.get("capabilities", []),
            "device": status.get("device", ""),
            "message": status.get("message", ""),
        }
    ]


def _event_allowed(event_type: str) -> bool:
    if event_type == "admin_live_test":
        return True
    expected = {"voice_only": "voice_mode_ended", "periodic_ordering": "ordering_periodic"}.get(capture_mode())
    return expected is not None and event_type == expected


def _canonical(value: object, allowed: set[str], default: str = "undetermined") -> str:
    candidate = str(value or "").strip().lower().replace(" ", "_")
    return candidate if candidate in allowed else default


def _record(event_type: str, model: str, signals: dict, *, failed: bool = False) -> dict:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": EVENT_LABELS.get(event_type, event_type),
        "model": model,
        "emotion": "undetermined" if failed else _canonical(signals.get("emotion"), EMOTIONS),
        "intensity": "undetermined" if failed else _canonical(signals.get("intensity"), INTENSITIES),
        "expression": "not_observed" if failed else str(signals.get("facial") or "not_observed")[:120],
        "voice": "not_observed" if failed else str(signals.get("vocal") or "not_observed")[:120],
        "description": (
            "模型未能完成本次分析；未保存媒體、提示詞或逐字稿。"
            if failed
            else str(signals.get("description") or "未提供整體描述")[:600]
        ),
    }
    return emotion_log_repository.append_record(row)


async def analyze_event(
    *,
    session_id: str,
    media_path: str,
    event_type: str,
    model_profile: str = MODEL_PROFILE,
    prompt: str = "",
    **_ignored,
) -> dict:
    """Submit one capture. Skips are not records; submitted failures are safe minimal records."""
    if not _event_allowed(event_type):
        return {"status": "skipped", "reason": "disabled_or_mode_mismatch"}
    if model_profile != MODEL_PROFILE:
        return {"status": "error", "reason": "model_profile_not_supported"}
    ready = model_profiles()[0]
    if not ready["ready"]:
        return {
            "status": "skipped",
            "reason": "model_not_ready",
            "provider": ready,
        }

    suffix = os.path.splitext(media_path)[1].lower()
    media_mode = "audio_only" if suffix in {".wav", ".mp3", ".m4a", ".ogg", ".flac"} else "video_audio"
    request = MultimodalEvidenceRequest(
        media_path=media_path,
        question=(prompt or default_prompt())[:20_000],
        media_mode=media_mode,
        session_ref=str(session_id)[:80],
        event_type=event_type,
        timeout_seconds=float(config.get("EMOTION_TIMEOUT_SEC", 120) or 120),
        skip_quality_check=True,
        prompt_version="emotion-single-pass-v1",
    )
    try:
        evidence = await asyncio.to_thread(collect_evidence, request, enabled=True)
    except Exception:
        # An unreported failure here is indistinguishable from a model that
        # simply saw nothing, which leaves the Admin diagnostic with no way to
        # tell an operator what to fix.
        logger.exception("emotion_analysis_failed event_type=%s profile=%s", event_type, model_profile)
        row = await asyncio.to_thread(_record, event_type, model_profile, {}, failed=True)
        return {"status": "error", "reason": "analysis_failed", "emotion": "undetermined", "record": row}
    if evidence.status == "skipped" or evidence.quality == "skipped":
        return {"status": "skipped", "reason": "incomplete_capture"}
    if not evidence.has_evidence:
        detail = str(evidence.safe_error or evidence.quality or "")[:200]
        logger.warning(
            "emotion_analysis_no_evidence event_type=%s profile=%s provider=%s detail=%s",
            event_type,
            model_profile,
            evidence.provider,
            detail or "unknown",
        )
        row = await asyncio.to_thread(_record, event_type, model_profile, {}, failed=True)
        return {
            "status": "error",
            "reason": "analysis_failed",
            "detail": detail,
            "emotion": "undetermined",
            "record": row,
        }
    row = await asyncio.to_thread(_record, event_type, model_profile, dict(evidence.signals or {}))
    return {
        "status": "ok",
        "emotion": str((evidence.signals or {}).get("emotion") or "undetermined")[:40],
        "record": row,
    }


async def analyze_live_diagnostic(media_path: str, *, model_profile: str = MODEL_PROFILE, prompt: str = "") -> dict:
    return await analyze_event(
        session_id="admin-test",
        media_path=media_path,
        event_type="admin_live_test",
        model_profile=model_profile,
        prompt=prompt,
    )
