"""The service must answer while its optional capabilities are still warming.

Blocking startup made every restart an outage: uvicorn answered nothing until
STT, RAG and the voice model had loaded, while Docker had already published the
port, so Admin and Kiosk device verification hung with nothing to react to.
"""

import asyncio

from fastapi.testclient import TestClient

from bootstrap import startup
from main import app


async def _no_warmup():
    return None


def _without_real_warmup(monkeypatch) -> None:
    """Keep the real model loading out of the way so state stays declared."""

    monkeypatch.setattr(startup, "_background_init_once", _no_warmup)
    monkeypatch.setattr(startup, "_background_init_done", False)


def _declare_warmup(monkeypatch, state: dict[str, str], started: bool = True) -> None:
    monkeypatch.setattr(startup, "_warmup_state", dict(state))
    monkeypatch.setattr(startup, "_warmup_started", started)


def test_http_service_answers_while_capability_warmup_is_still_running(monkeypatch):
    finished = asyncio.Event()

    async def _slow_warmup():
        with startup._warmup_lock:
            startup._warmup_started = True
        await asyncio.sleep(2)
        finished.set()

    monkeypatch.setattr(startup, "_background_init_once", _slow_warmup)
    monkeypatch.setattr(startup, "_background_init_done", False)

    with TestClient(app) as client:
        # Reaching this line before warm-up finishes is the whole contract.
        assert not finished.is_set()
        response = client.get("/api/admin/auth/me")

    assert response.status_code == 200
    assert response.json()["access"] == "device_admin"


def test_readiness_reports_optional_capabilities_without_deciding_readiness(monkeypatch):
    _without_real_warmup(monkeypatch)

    with TestClient(app) as client:
        _declare_warmup(
            monkeypatch,
            {"stt": "pending", "tts": "skipped", "rag": "ready", "voice_llm": "failed"},
        )
        body = client.get("/ready").json()

    assert body["warming_capabilities"] == ["stt"]
    assert body["degraded_optional_dependencies"] == ["voice_llm"]
    assert body["optional_capabilities"]["rag"] == "ready"
    # Readiness is decided by the required checks alone. A warming or failed
    # optional capability may be reported, but never counted.
    assert set(body["required_checks"]).isdisjoint(body["optional_capabilities"])
    assert body["ready"] == all(check["status"] in {"ok", "skipped"} for check in body["required_checks"].values())


def test_a_capability_that_never_started_warming_is_not_gated(monkeypatch):
    _declare_warmup(
        monkeypatch,
        {name: "pending" for name in startup._WARMUP_CAPABILITIES},
        started=False,
    )

    assert startup.capability_warm("stt") is True


def test_a_warming_capability_is_gated_until_it_is_ready(monkeypatch):
    _declare_warmup(
        monkeypatch,
        {"stt": "pending", "tts": "skipped", "rag": "pending", "voice_llm": "ready"},
    )

    assert startup.capability_warm("stt") is False
    assert startup.capability_warm("tts") is True
    assert startup.capability_warm("voice_llm") is True


def test_voice_refuses_a_turn_while_its_model_is_still_loading(monkeypatch):
    """A customer must not silently pay the model load as Voice Response Wait."""

    _without_real_warmup(monkeypatch)

    with TestClient(app) as client:
        _declare_warmup(
            monkeypatch,
            {"stt": "pending", "tts": "skipped", "rag": "ready", "voice_llm": "ready"},
        )
        response = client.post(
            "/api/ask/stream",
            data={"session_id": "session-warming"},
            files={"media": ("turn.webm", b"not-audio", "audio/webm")},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "voice_capability_warming"


def test_voice_is_accepted_once_its_model_is_ready(monkeypatch):
    _without_real_warmup(monkeypatch)

    with TestClient(app) as client:
        _declare_warmup(
            monkeypatch,
            {"stt": "ready", "tts": "skipped", "rag": "ready", "voice_llm": "ready"},
        )
        response = client.post(
            "/api/ask/stream",
            data={"session_id": "session-ready"},
            files={"media": ("turn.webm", b"not-audio", "audio/webm")},
        )

    # Whatever the turn then does, it was not refused by the warm-up gate.
    assert response.status_code != 503
