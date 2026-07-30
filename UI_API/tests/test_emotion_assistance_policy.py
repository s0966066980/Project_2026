from modules.assistance_policy import decide
from services import emotion_service


def _evidence(**overrides):
    return {
        "status": "ok",
        "emotion": "confused",
        "confidence": 0.9,
        "repaired_fields": [],
        **overrides,
    }


def test_shadow_policy_is_eligible_but_never_applied():
    decision = decide(_evidence(), mode="shadow", session_id="s1", rollout_percent=100)

    assert decision["eligible"] is True
    assert decision["applied"] is False
    assert decision["experiment_group"] == "shadow"
    assert decision["transaction_authority"] == "none"


def test_active_policy_respects_confidence_and_rollout():
    control = decide(_evidence(), mode="active", session_id="s1", rollout_percent=0)
    low_confidence = decide(
        _evidence(confidence=0.4),
        mode="active",
        confidence_threshold=0.7,
        session_id="s1",
        rollout_percent=100,
    )
    treatment = decide(_evidence(), mode="active", session_id="s1", rollout_percent=100)

    assert control["experiment_group"] == "control"
    assert control["applied"] is False
    assert low_confidence["eligible"] is False
    assert low_confidence["applied"] is False
    assert treatment["experiment_group"] == "treatment"
    assert treatment["applied"] is True


def test_repaired_emotion_cannot_change_customer_reply():
    decision = decide(
        _evidence(repaired_fields=["emotion"]),
        mode="active",
        session_id="s1",
        rollout_percent=100,
    )

    assert decision["eligible"] is False
    assert decision["reason"] == "emotion_repaired"


def test_summary_keeps_accuracy_and_outcome_claims_gated():
    logs = [
        {
            "event_type": "voice_llm_influence",
            "session_id": "treatment-session",
            "experiment_group": "treatment",
            "influence_status": "applied",
        },
        {
            "event_type": "voice_llm_influence",
            "session_id": "control-session",
            "experiment_group": "control",
            "influence_status": "control",
        },
        {
            "event_type": "assistance_outcome",
            "session_id": "treatment-session",
            "outcome": "checkout_completed",
        },
        {
            "event_type": "human_evaluation",
            "usable": True,
            "model_emotion": "confused",
            "observed_emotion": "confused",
        },
    ]

    summary = emotion_service.build_assistance_summary(logs)

    assert summary["exact_label_agreement"] == 1.0
    assert summary["groups"]["treatment"]["checkout_rate"] == 1.0
    assert summary["groups"]["control"]["checkout_rate"] == 0.0
    assert summary["accuracy_assessment"] == "insufficient_human_labels"
    assert summary["outcome_assessment"] == "insufficient_experiment_sessions"
