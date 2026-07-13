"""Milestone 8C: failure injection and recovery contracts (internal)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

TENANT = UUID("00000000-0000-4000-8000-000000000001")


def test_worker_unknown_handler_does_not_succeed() -> None:
    from datetime import datetime, timezone

    from models.worker_jobs import BackgroundJob, JobStatus
    from services import worker_service

    worker_service.clear_handlers()
    now = datetime.now(timezone.utc)
    job = BackgroundJob(
        job_id=uuid4(),
        tenant_id=TENANT,
        store_id=None,
        job_type="unknown.job.type",
        payload_ref={},
        status=JobStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
        idempotency_key="fail-inj-1",
        scheduled_at=now,
        available_at=now,
        visibility_timeout_seconds=30,
    )
    # Process should fail closed for unknown handlers (via unknown handler path).
    result = worker_service._unknown_handler(job)
    assert result.success is False
    assert result.retryable is False
    assert "unknown" in (result.safe_error or "")


def test_outbox_requires_sink_ack_before_published() -> None:
    from services.outbox_delivery_router import OutboxDeliveryRouter
    from models.worker_jobs import OutboxDeliveryResult

    calls: list[str] = []

    def fail_then_ok(event):
        calls.append(str(event.get("event_type") or ""))
        if len(calls) == 1:
            return OutboxDeliveryResult(success=False, retryable=True, safe_error="sink_down")
        return OutboxDeliveryResult(
            success=True,
            retryable=False,
            delivery_id="d1",
            provider="test",
            acknowledged_at="t",
        )

    router = OutboxDeliveryRouter()
    router.register("order_completed", fail_then_ok)
    first = router.deliver({"event_type": "order_completed", "event_id": "e1"})
    assert first.success is False
    second = router.deliver({"event_type": "order_completed", "event_id": "e1"})
    assert second.success is True
    assert second.delivery_id == "d1"


def test_analytics_duplicate_event_is_idempotent(tmp_path, monkeypatch) -> None:
    from services import analytics_pipeline_service

    monkeypatch.setattr(analytics_pipeline_service.config, "LEARNING_DATA_DIR", str(tmp_path))
    env = analytics_pipeline_service.build_envelope(
        event_type="checkout.completed",
        payload={"total": 10},
        tenant_id=TENANT,
        event_id="inj-1",
    )
    sink = analytics_pipeline_service.InMemoryAnalyticsSink()
    assert analytics_pipeline_service.publish(env, sink=sink) is True
    assert analytics_pipeline_service.publish(env, sink=sink) is False


def test_llm_gateway_timeout_does_not_block_on_thread_exit() -> None:
    import time

    from models.llm import LLMAdapterResult, LLMModelPolicy, LLMRequest
    from services import llm_gateway_service

    class Slow:
        name = "ollama"

        def generate(self, request):
            time.sleep(0.3)
            return LLMAdapterResult(
                content="",
                provider="ollama",
                model="m",
                latency_ms=300,
                usage=None,
                finish_reason="stop",
                safe_error="",
                retryable=False,
                parsed=None,
            )

    started = time.perf_counter()
    response = llm_gateway_service.generate(
        LLMRequest(
            task="inj",
            system_prompt="s",
            user_prompt="u",
            model_policy=LLMModelPolicy.LOCAL_ONLY,
            timeout_seconds=0.05,
            expect_json=False,
            max_retries=0,
        ),
        adapters={"ollama": Slow()},
    )
    elapsed = time.perf_counter() - started
    assert response.finish_reason == "timeout"
    assert elapsed < 0.25
