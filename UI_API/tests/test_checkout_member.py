import asyncio
import importlib


def test_process_checkout_calls_finalize(monkeypatch):
    from services import checkout_service
    importlib.reload(checkout_service)
    monkeypatch.setattr(checkout_service.database, "record_final_checkout",
                        lambda *a, **k: {"is_success": True})
    monkeypatch.setattr(checkout_service, "mark_latest_intervention_checkout", lambda *a, **k: None)
    monkeypatch.setattr(checkout_service.session_repository, "get_session_history", lambda sid: [])
    monkeypatch.setattr(checkout_service.session_repository, "archive_session", lambda sid: None)
    monkeypatch.setattr(checkout_service.log_repository, "get_session_logs", lambda: [])

    seen = {}
    def fake_finalize(session_id, cart_ids, total, ok):
        seen["args"] = (session_id, cart_ids, total, ok)
    monkeypatch.setattr(checkout_service.member_service, "finalize_checkout", fake_finalize)

    out = asyncio.run(checkout_service.process_checkout("s1", [], ["MCD001"], 0, [], 200))
    assert out["status"] == "success"
    assert seen["args"] == ("s1", ["MCD001"], 200, True)


def test_finalize_exception_does_not_break_checkout(monkeypatch):
    from services import checkout_service
    importlib.reload(checkout_service)
    monkeypatch.setattr(checkout_service.database, "record_final_checkout",
                        lambda *a, **k: {"is_success": False})
    monkeypatch.setattr(checkout_service, "mark_latest_intervention_checkout", lambda *a, **k: None)
    monkeypatch.setattr(checkout_service.session_repository, "get_session_history", lambda sid: [])
    monkeypatch.setattr(checkout_service.session_repository, "archive_session", lambda sid: None)
    monkeypatch.setattr(checkout_service.log_repository, "get_session_logs", lambda: [])

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(checkout_service.member_service, "finalize_checkout", boom)

    out = asyncio.run(checkout_service.process_checkout("s1", [], ["MCD001"], 0, [], 200))
    assert out["status"] == "success"
