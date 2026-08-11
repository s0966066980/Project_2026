"""P1 Admin surface contracts that keep pre-pilot scorecards retired."""

from dataclasses import fields
from inspect import signature
from pathlib import Path

from modules.analytics.application import build_effectiveness_report
from modules.analytics.contracts import EffectivenessReport

from api.v1.contracts import RecommendationEffectivenessDTO
from models.settings_contract import SettingsUpdateRequest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET_SETTING_KEYS = {
    "RECOMMENDATION_PURCHASE_RATE_TARGET",
    "RECOMMENDATION_IGNORE_RATE_GUARDRAIL",
}
TARGET_REPORT_FIELDS = {
    "purchase_rate_target",
    "ignore_rate_guardrail",
    "target_status",
}


def test_recommendation_targets_are_not_settings_or_report_contracts():
    assert TARGET_SETTING_KEYS.isdisjoint(SettingsUpdateRequest.model_fields)
    assert TARGET_REPORT_FIELDS.isdisjoint(RecommendationEffectivenessDTO.model_fields)
    assert TARGET_REPORT_FIELDS.isdisjoint({field.name for field in fields(EffectivenessReport)})
    assert "targets" not in signature(build_effectiveness_report).parameters


def test_admin_has_no_recommendation_target_controls_or_target_judgement():
    sources = [
        PROJECT_ROOT / "frontend/admin/admin.html",
        PROJECT_ROOT / "frontend/admin/modules/settingsAdmin.js",
        PROJECT_ROOT / "frontend/admin/modules/recommendationEventsAdmin.js",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    forbidden = TARGET_SETTING_KEYS | TARGET_REPORT_FIELDS | {
        "推薦表現目標",
        "inp-recommendation-purchase-target",
        "inp-recommendation-ignore-guardrail",
    }

    still_present = {token for token in forbidden if token in combined}
    assert still_present == set(), f"Admin still exposes recommendation targets: {sorted(still_present)}"


def test_admin_emotion_surface_has_no_legacy_intervention_or_evidence_workflows():
    sources = [
        PROJECT_ROOT / "frontend/admin/admin.html",
        PROJECT_ROOT / "frontend/admin/admin.js",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    forbidden = {
        "page-emotion-legacy",
        "成效證據",
        "assistance_summary",
        "emotion/intervention_logs",
        "human_evaluations",
        "analyze_ordering_round",
        "EMOTION_ASSISTANCE_MODE",
        "EMOTION_ANALYSIS_MODE",
    }
    assert {token for token in forbidden if token in combined} == set()
    assert "即時影音情緒測試" in combined
    assert "專案核心大腦" in combined
