"""Worker contracts for the campaign notification-copy batch surface."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from models.worker_jobs import BackgroundJob, JobStatus
from services import worker_handlers

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _job(batch_id: str) -> BackgroundJob:
    now = datetime.now(timezone.utc)
    tenant_id = uuid4()
    return BackgroundJob(
        job_id=uuid4(),
        tenant_id=tenant_id,
        store_id=uuid4(),
        job_type="ai.background",
        payload_ref={"kind": "push_copy_batch", "batch_id": batch_id},
        status=JobStatus.PENDING,
        attempt_count=1,
        max_attempts=3,
        idempotency_key=f"push-copy-{batch_id}",
        scheduled_at=now,
        available_at=now,
        visibility_timeout_seconds=60,
    )


def test_push_copy_batch_continues_after_item_failure_and_reports_partial_success(monkeypatch):
    from capabilities import catalog
    from repositories import push_copy_batch_repository, push_copy_repository
    from services import push_copy_authoring_service

    batch = {"item_ids": ["item-a", "missing", "item-b"], "succeeded": 0, "failed": 0}
    saved: list[tuple[str, dict]] = []
    finished: list[str] = []

    monkeypatch.setattr(
        catalog,
        "list_active_items",
        lambda: [{"id": "item-a", "name": "Tea"}, {"id": "item-b", "name": "Cake"}],
    )
    monkeypatch.setattr(push_copy_batch_repository, "get_batch", lambda scope, batch_id: batch)
    monkeypatch.setattr(push_copy_batch_repository, "mark_running", lambda scope, batch_id: None)

    def record_item_result(scope, batch_id, *, ok, error=""):
        batch["succeeded" if ok else "failed"] += 1

    monkeypatch.setattr(push_copy_batch_repository, "record_item_result", record_item_result)
    monkeypatch.setattr(
        push_copy_batch_repository,
        "finish_batch",
        lambda scope, batch_id, *, status: finished.append(status),
    )
    monkeypatch.setattr(push_copy_repository, "list_copy_scoped", lambda scope: {})
    monkeypatch.setattr(
        push_copy_repository,
        "save_copy_scoped",
        lambda item_id, entry, scope, actor_id: saved.append((item_id, entry)),
    )

    def draft_copy(item, *, slot):
        if item["id"] == "item-b":
            return None, "provider timeout", []
        return "Try our tea today.", "", []

    monkeypatch.setattr(push_copy_authoring_service, "draft_copy", draft_copy)
    worker_handlers.clear_side_effect_ledger()

    result = worker_handlers.handle_ai_background(_job("batch-partial"))

    assert result.success is True
    assert batch == {"item_ids": ["item-a", "missing", "item-b"], "succeeded": 1, "failed": 2}
    assert saved == [("item-a", {"base_copy": "Try our tea today."})]
    assert finished == ["succeeded"]


def test_push_copy_batch_is_failed_only_when_every_item_fails(monkeypatch):
    from capabilities import catalog
    from repositories import push_copy_batch_repository, push_copy_repository
    from services import push_copy_authoring_service

    batch = {"item_ids": ["item-a"], "succeeded": 0, "failed": 0}
    finished: list[str] = []

    monkeypatch.setattr(catalog, "list_active_items", lambda: [{"id": "item-a", "name": "Tea"}])
    monkeypatch.setattr(push_copy_batch_repository, "get_batch", lambda scope, batch_id: batch)
    monkeypatch.setattr(push_copy_batch_repository, "mark_running", lambda scope, batch_id: None)
    monkeypatch.setattr(
        push_copy_batch_repository,
        "record_item_result",
        lambda scope, batch_id, *, ok, error="": batch.__setitem__("failed", batch["failed"] + 1),
    )
    monkeypatch.setattr(
        push_copy_batch_repository,
        "finish_batch",
        lambda scope, batch_id, *, status: finished.append(status),
    )
    monkeypatch.setattr(push_copy_repository, "list_copy_scoped", lambda scope: {})
    monkeypatch.setattr(push_copy_authoring_service, "draft_copy", lambda item, *, slot: (None, "provider down", []))
    worker_handlers.clear_side_effect_ledger()

    result = worker_handlers.handle_ai_background(_job("batch-failed"))

    assert result.success is True
    assert batch["failed"] == 1
    assert finished == ["failed"]
