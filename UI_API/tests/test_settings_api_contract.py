"""The settings surface must validate what it stores and never broadcast credentials."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.auth_test_support import authenticate_client, configure_admin_session, configure_device_session

import config


@pytest.fixture
def client(monkeypatch) -> TestClient:
    from backend import app_factory

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    configure_admin_session(monkeypatch)
    configure_device_session(monkeypatch)
    test_client = TestClient(app_factory.create_app())
    authenticate_client(test_client, admin=True, device=True)
    return test_client


@pytest.fixture
def captured_broadcast(monkeypatch) -> list[dict]:
    from realtime import event_bus

    events: list[dict] = []

    async def _capture(event: dict):
        events.append(event)
        return event

    monkeypatch.setattr(event_bus, "publish_event", _capture)
    return events


@pytest.fixture
def stored(monkeypatch) -> dict:
    from repositories import commercial_settings_repository

    saved: dict = {}

    def _save(data, scope, *, actor_id=None):
        saved.update(data)
        return dict(saved)

    monkeypatch.setattr(commercial_settings_repository, "save_settings_scoped", _save)
    return saved


def test_settings_broadcast_carries_only_public_keys(client, captured_broadcast, stored):
    response = client.post("/api/settings", json={"LLM_ROUTING_POLICY": "cloud_first"})

    assert response.status_code == 200
    broadcast = captured_broadcast[0]["payload"]["settings"]
    assert set(broadcast) == set(config.PUBLIC_SETTINGS_KEYS)
    assert not (set(broadcast) & config.CREDENTIAL_SETTING_KEYS)
    assert "STT_API_URL" not in broadcast
    assert "LLM_ROUTING_POLICY" not in broadcast


def test_settings_reject_credentials_with_an_actionable_message(client, stored):
    response = client.post("/api/settings", json={"STT_API_KEY": "sk-secret", "STT_MODEL": "small"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "credential_not_accepted"
    assert "sk-secret" not in response.text
    assert stored == {}


def test_settings_reject_unknown_keys(client, stored):
    response = client.post("/api/settings", json={"MODEL_NMAE": "typo"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "settings_invalid"
    assert stored == {}


def test_settings_reject_out_of_range_values_with_a_field_path(client, stored):
    response = client.post("/api/settings", json={"OLLAMA_TEMPERATURE": 2.4})

    assert response.status_code == 422
    details = response.json()["detail"]["field_errors"]
    assert any(item["path"] == "OLLAMA_TEMPERATURE" for item in details)
    assert stored == {}


def test_a_tab_save_only_writes_the_keys_it_sent(client, stored):
    response = client.post("/api/settings", json={"STT_PROVIDER": "openai_compatible", "STT_MODEL": "whisper-1"})

    assert response.status_code == 200
    assert stored == {"STT_PROVIDER": "openai_compatible", "STT_MODEL": "whisper-1"}


def test_llm_routing_and_traffic_are_readable_by_an_admin(client):
    readiness = client.get("/api/settings/llm-routing")
    traffic = client.get("/api/settings/llm-traffic")

    assert readiness.status_code == 200
    assert set(readiness.json()) >= {"policy", "cloud_provider", "local", "cloud", "degraded"}
    assert traffic.status_code == 200
    assert set(traffic.json()) == {"providers", "fallbacks", "total"}
