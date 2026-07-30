import json
import logging
from datetime import datetime

from fastapi.testclient import TestClient


def test_runtime_retention_removes_expired_rows_and_keeps_unparseable(tmp_path, monkeypatch):
    from services import observability_service

    monkeypatch.setattr(observability_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        observability_service.config,
        "get",
        lambda key, default=None: 7 if key == "LOG_RETENTION_DAYS" else default,
    )

    path = tmp_path / "session_logs.json"
    path.write_text(json.dumps([
        {"timestamp": "2026-06-01T00:00:00", "value": "old"},
        {"timestamp": "2026-07-01T00:00:00", "value": "new"},
        {"timestamp": "not-a-date", "value": "kept"},
    ], ensure_ascii=False), encoding="utf-8")

    result = observability_service.apply_runtime_retention(now=datetime(2026, 7, 4, 0, 0, 0))
    rows = json.loads(path.read_text(encoding="utf-8"))

    assert result["enabled"] is True
    assert rows == [
        {"timestamp": "2026-07-01T00:00:00", "value": "new"},
        {"timestamp": "not-a-date", "value": "kept"},
    ]


def test_runtime_retention_can_be_disabled(tmp_path, monkeypatch):
    from services import observability_service

    monkeypatch.setattr(observability_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        observability_service.config,
        "get",
        lambda key, default=None: 0 if key == "LOG_RETENTION_DAYS" else default,
    )

    result = observability_service.apply_runtime_retention(now=datetime(2026, 7, 4, 0, 0, 0))

    assert result == {"enabled": False, "retention_days": 0, "files": []}


def test_json_log_formatter_outputs_structured_request_fields():
    from services import observability_service

    record = logging.LogRecord(
        name="ui_api.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_test"
    record.method = "GET"
    record.path = "/api/public_settings"
    record.status_code = 200
    record.duration_ms = 12.34
    record.client_host = "127.0.0.1"
    record.event = "http_request"

    payload = json.loads(observability_service.JsonLogFormatter().format(record))

    assert payload["event"] == "http_request"
    assert payload["request_id"] == "req_test"
    assert payload["path"] == "/api/public_settings"
    assert payload["status_code"] == 200
    assert "query" not in payload


def test_create_app_adds_request_id_header(monkeypatch):
    import app_factory

    import config

    async def fake_background_init():
        return None

    monkeypatch.setattr(app_factory, "background_init", fake_background_init)
    monkeypatch.setattr(app_factory.observability_service, "apply_runtime_retention", lambda: {})
    monkeypatch.setattr(config, "APP_ENV", "test")

    client = TestClient(app_factory.create_app())
    response = client.get("/api/public_settings", headers={"X-Request-Id": "req_existing"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "req_existing"
