import importlib


def _service(tmp_path, monkeypatch):
    from services import rag_alert_service
    importlib.reload(rag_alert_service)
    monkeypatch.setattr(rag_alert_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr(rag_alert_service.config, "get", lambda key, default=None: {
        "RAG_ALERT_MAX_RECORDS": 1000,
        "RAG_ALERT_WEBHOOK_ENABLED": False,
    }.get(key, default))
    return rag_alert_service


def test_create_alert_deduplicates_open_alert(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)

    first, first_created = service.create_alert(
        "rag_rebuild_validation_failed",
        message="validation failed",
        errors=[{"path": "broken.json", "message": "invalid json"}],
        source_dir="/tmp/rag",
    )
    second, second_created = service.create_alert(
        "rag_rebuild_validation_failed",
        message="validation failed",
        errors=[{"path": "broken.json", "message": "invalid json"}],
        source_dir="/tmp/rag",
    )

    assert first_created is True
    assert second_created is False
    assert first["alert_id"] == second["alert_id"]
    assert second["count"] == 2
    assert len(service.list_alerts()) == 1


def test_acknowledge_and_resolve_alert(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    alert, _ = service.create_alert("rag_health_degraded", message="health degraded")

    acknowledged, errors = service.acknowledge_alert(alert["alert_id"], actor="tester")
    assert errors == []
    assert acknowledged["status"] == "acknowledged"
    assert acknowledged["acknowledged_by"] == "tester"

    resolved, errors = service.resolve_alert(alert["alert_id"], actor="tester")
    assert errors == []
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "tester"


def test_webhook_failure_is_recorded_without_raising(tmp_path, monkeypatch):
    from services import rag_alert_service
    importlib.reload(rag_alert_service)
    monkeypatch.setattr(rag_alert_service.config, "LEARNING_DATA_DIR", str(tmp_path / "learning_data"))
    monkeypatch.setattr(rag_alert_service.config, "get", lambda key, default=None: {
        "RAG_ALERT_MAX_RECORDS": 1000,
        "RAG_ALERT_WEBHOOK_ENABLED": True,
        "RAG_ALERT_WEBHOOK_URL": "http://127.0.0.1:1/unavailable",
        "RAG_ALERT_WEBHOOK_TOKEN": "secret",
        "RAG_ALERT_WEBHOOK_TIMEOUT_SEC": 0.1,
    }.get(key, default))

    alert, created = rag_alert_service.create_alert("rag_rebuild_partial_failed", message="partial")

    assert created is True
    assert alert["notification"]["enabled"] is True
    assert alert["notification"]["status"] == "failed"
