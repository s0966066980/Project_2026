"""付款失敗事件由 Kiosk 傳到 Admin 的公開整合契約。"""

from fastapi.testclient import TestClient


def test_payment_staff_request_reaches_admin_without_emotion_payload(monkeypatch) -> None:
    from backend import app_factory
    from repositories import interaction_event_repository

    monkeypatch.setattr(app_factory.config, "validate_startup_config", lambda: None)
    monkeypatch.setattr(
        interaction_event_repository,
        "append_interaction_event_scoped",
        lambda event, _scope: event,
    )
    client = TestClient(app_factory.create_app())
    payload = {
        "session_id": "kiosk-payment-timeout",
        "page_id": "payment_page",
        "event_type": "payment_staff_requested",
        "button_id": "paymentCountdownAssistButton",
        "metadata": {},
    }

    with client.websocket_connect("/ws/admin/admin") as websocket:
        response = client.post("/api/interaction_event", json=payload)
        notification = websocket.receive_json()

    assert response.status_code == 200
    assert notification["type"] == "staff_notify"
    assert notification["payload"]["reason"] == "payment_staff_requested"
    assert notification["payload"]["kiosk_name"]
    assert "emotion" not in notification["payload"]
    assert "assist_response" not in notification["payload"]
