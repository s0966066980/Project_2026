import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from main import app
from models.commercial_scope import LEGACY_DEFAULT_SCOPE
from modules.voice_evidence.module import VoiceEvidenceModule
from modules.voice_evidence.sqlite_store import SQLiteVoiceEvidenceStore
from routes import voice_evidence_routes

pytestmark = [pytest.mark.contract, pytest.mark.integration]


def test_voice_evidence_route_is_metadata_only_and_has_separate_permission(tmp_path, monkeypatch):
    module = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.sqlite3"))
    module.project_terminal_turn(
        scope=LEGACY_DEFAULT_SCOPE,
        terminal={
            "voice_turn_id": "turn-route-1",
            "observed_at": "2026-08-14T09:30:00+08:00",
            "status": "completed",
            "user_text": "顧客電話 0912345678",
            "assistant_text": "已完成",
        },
    )
    allow = {"value": True}

    def authorize(_request, permission):
        if permission == "voice.evidence.summary" and not allow["value"]:
            raise HTTPException(status_code=403, detail={"code": "permission_denied"})
        return object()

    monkeypatch.setattr(voice_evidence_routes, "authorize_admin_request", authorize)
    monkeypatch.setattr(voice_evidence_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(voice_evidence_routes.voice_evidence_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/voice-evidence",
            params={
                "observed_from": "2026-08-14T00:00:00+08:00",
                "observed_to": "2026-08-15T00:00:00+08:00",
            },
        )
        assert response.status_code == 200
        record = response.json()["records"][0]
        assert record["voice_turn_id"] == "turn-route-1"
        assert "user_text" not in record
        assert "assistant_text" not in record
        assert "0912345678" not in response.text

        allow["value"] = False
        denied = client.get(
            "/api/v1/voice-evidence",
            params={
                "observed_from": "2026-08-14T00:00:00+08:00",
                "observed_to": "2026-08-15T00:00:00+08:00",
            },
        )
        assert denied.status_code == 403


def test_voice_evidence_route_is_versioned_with_stable_cursor_filters():
    paths = {route.path for route in voice_evidence_routes.create_router().routes}
    assert "/api/v1/voice-evidence" in paths


def test_expired_voice_evidence_window_is_not_reported_as_zero(tmp_path, monkeypatch):
    module = VoiceEvidenceModule(store=SQLiteVoiceEvidenceStore(tmp_path / "evidence.sqlite3"))
    monkeypatch.setattr(voice_evidence_routes, "authorize_admin_request", lambda _request, _permission: object())
    monkeypatch.setattr(voice_evidence_routes, "scope_from_admin_principal", lambda _principal: LEGACY_DEFAULT_SCOPE)
    monkeypatch.setattr(voice_evidence_routes.voice_evidence_runtime, "default_module", lambda: module)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/voice-evidence",
            params={
                "observed_from": "2025-01-01T00:00:00+00:00",
                "observed_to": "2025-01-02T00:00:00+00:00",
            },
        )

    assert response.status_code == 410
    assert "evidence_expired" in response.text
