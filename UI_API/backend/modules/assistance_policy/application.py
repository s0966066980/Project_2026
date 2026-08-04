"""Convert emotion evidence into low-risk ordering assistance adjustments."""

from __future__ import annotations

import hashlib
from typing import Any


_BARRIER_EMOTIONS = {
    "anxious",
    "confused",
    "frustrated",
    "nervous",
    "焦慮",
    "困惑",
    "挫折",
    "緊張",
}


def decide(
    evidence: dict[str, Any] | None,
    *,
    mode: str = "shadow",
    confidence_threshold: float = 0.7,
    session_id: str = "",
    rollout_percent: int = 0,
) -> dict[str, Any]:
    """Return allowed response adjustments without granting transaction authority."""

    resolved_mode = str(mode or "shadow").strip().lower()
    if resolved_mode not in {"disabled", "shadow", "active"}:
        resolved_mode = "shadow"
    reference = dict(evidence or {})
    try:
        confidence = float(reference.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    threshold = min(1.0, max(0.0, float(confidence_threshold)))
    rollout = min(100, max(0, int(rollout_percent or 0)))
    bucket = int(
        hashlib.sha256(str(session_id or "").encode("utf-8")).hexdigest()[:8],
        16,
    ) % 100
    experiment_group = (
        "shadow"
        if resolved_mode == "shadow"
        else "treatment"
        if resolved_mode == "active" and bucket < rollout
        else "control"
        if resolved_mode == "active"
        else "disabled"
    )
    emotion = str(reference.get("emotion") or "").strip().casefold()
    repaired_fields = {str(value) for value in reference.get("repaired_fields") or []}
    eligible = bool(
        resolved_mode != "disabled"
        and emotion in _BARRIER_EMOTIONS
        and confidence >= threshold
        and "emotion" not in repaired_fields
        and reference.get("status") == "ok"
    )
    applied = eligible and resolved_mode == "active" and experiment_group == "treatment"
    adjustments = ["shorter_response", "single_clarifying_question", "confirm_before_cart_change"] if eligible else []
    return {
        "mode": resolved_mode,
        "eligible": eligible,
        "applied": applied,
        "confidence": round(confidence, 4),
        "confidence_threshold": threshold,
        "rollout_percent": rollout,
        "experiment_group": experiment_group,
        "experiment_bucket": bucket,
        "adjustments": adjustments,
        "reason": (
            "disabled" if resolved_mode == "disabled"
            else "emotion_repaired" if "emotion" in repaired_fields
            else "low_confidence" if confidence < threshold
            else "no_ordering_barrier" if emotion not in _BARRIER_EMOTIONS
            else "shadow_observation" if resolved_mode == "shadow"
            else "rollout_control" if experiment_group == "control"
            else "allowed_low_risk_adjustment"
        ),
        "transaction_authority": "none",
    }
