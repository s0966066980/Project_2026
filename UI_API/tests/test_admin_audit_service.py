import importlib

import pytest


@pytest.fixture
def audit_service(tmp_path, monkeypatch):
    from repositories import admin_audit_repository
    importlib.reload(admin_audit_repository)
    monkeypatch.setattr(admin_audit_repository, "ADMIN_AUDIT_PATH", str(tmp_path / "admin_audit_logs.json"))
    from services import admin_audit_service
    importlib.reload(admin_audit_service)
    return admin_audit_service


def test_record_admin_action(audit_service):
    record = audit_service.record_admin_action(
        "member_delete",
        target_type="member",
        target_id="0912-***-678",
        metadata={"member_ref": "mem_x"},
    )

    assert record["audit_id"].startswith("aud_")
    assert record["action"] == "member_delete"
    assert record["target_id"] == "0912-***-678"
    assert audit_service.list_admin_audits()[-1]["metadata"]["member_ref"] == "mem_x"
