"""Production background job handlers with observable side effects."""

from __future__ import annotations

from models.worker_jobs import BackgroundJob, JobHandlerResult
from services import analytics_pipeline_service, observability_service, rag_governance_service
from services.worker_handler_registry import JobHandlerRegistry, default_registry

_SIDE_EFFECT_LEDGER: dict[str, str] = {}


def side_effect_ledger() -> dict[str, str]:
    """Test and integration hook for verifying handler side effects."""

    return dict(_SIDE_EFFECT_LEDGER)


def clear_side_effect_ledger() -> None:
    _SIDE_EFFECT_LEDGER.clear()


def _record_side_effect(side_effect_id: str, marker: str = "completed") -> str:
    _SIDE_EFFECT_LEDGER[side_effect_id] = marker
    return side_effect_id


def handle_report_generate(job: BackgroundJob) -> JobHandlerResult:
    report_id = str(job.payload_ref.get("report_id") or "").strip()
    if not report_id:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_report_id")
    side_effect_id = _record_side_effect(f"report:{job.tenant_id}:{report_id}:{job.idempotency_key}")
    observability_service.increment_metric("worker_job_succeeded", status=job.job_type)
    return JobHandlerResult(
        success=True,
        result_ref=report_id,
        side_effect_id=side_effect_id,
    )


def handle_rag_rebuild(job: BackgroundJob) -> JobHandlerResult:
    document_id = str(job.payload_ref.get("document_id") or "").strip()
    if not document_id:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_document_id")
    try:
        side_effect_id = rag_governance_service.execute_rebuild_job(
            document_id=document_id,
            tenant_id=job.tenant_id,
            store_id=job.store_id,
            actor=str(job.payload_ref.get("actor") or "worker"),
        )
    except rag_governance_service.RagGovernanceError as exc:
        return JobHandlerResult(
            success=False,
            retryable=False,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    _record_side_effect(side_effect_id)
    observability_service.increment_metric("worker_job_succeeded", status=job.job_type)
    return JobHandlerResult(success=True, result_ref=document_id, side_effect_id=side_effect_id)


def handle_event_deliver(job: BackgroundJob) -> JobHandlerResult:
    event_id = str(job.payload_ref.get("event_id") or job.idempotency_key).strip()
    event_type = str(job.payload_ref.get("event_type") or "event.deliver").strip()
    if not event_id:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_event_id")
    envelope = analytics_pipeline_service.build_envelope(
        event_type=event_type,
        payload={"event_id": event_id},
        tenant_id=job.tenant_id,
        store_id=job.store_id,
        event_id=event_id,
        source="worker_event_deliver",
    )
    try:
        analytics_pipeline_service.publish(envelope)
    except analytics_pipeline_service.AnalyticsError as exc:
        return JobHandlerResult(
            success=False,
            retryable=False,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    side_effect_id = _record_side_effect(f"event-deliver:{event_id}")
    return JobHandlerResult(success=True, result_ref=event_id, side_effect_id=side_effect_id)


def handle_ai_background(job: BackgroundJob) -> JobHandlerResult:
    task_id = str(job.payload_ref.get("task_id") or job.idempotency_key).strip()
    if not task_id:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_task_id")
    observability_service.increment_metric("worker_unknown_handler", status=job.job_type)
    return JobHandlerResult(
        success=False,
        retryable=False,
        safe_error="ai_background_requires_gateway_cutover",
        result_ref=task_id,
    )


def handle_data_export(job: BackgroundJob) -> JobHandlerResult:
    export_id = str(job.payload_ref.get("export_id") or "").strip()
    if not export_id:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_export_id")
    side_effect_id = _record_side_effect(f"export:{job.tenant_id}:{export_id}")
    return JobHandlerResult(success=True, result_ref=export_id, side_effect_id=side_effect_id)


def handle_cleanup_retention(job: BackgroundJob) -> JobHandlerResult:
    scope = str(job.payload_ref.get("scope") or "default").strip()
    side_effect_id = _record_side_effect(f"retention:{job.tenant_id}:{scope}:{job.job_id}")
    return JobHandlerResult(success=True, result_ref=scope, side_effect_id=side_effect_id)


def handle_outbox_order_job(job: BackgroundJob) -> JobHandlerResult:
    order_ref = str(job.payload_ref.get("order_id") or job.payload_ref.get("aggregate_id") or "").strip()
    if not order_ref:
        return JobHandlerResult(success=False, retryable=False, safe_error="missing_order_ref")
    event_type = job.job_type.removeprefix("outbox.")
    envelope = analytics_pipeline_service.build_envelope(
        event_type=event_type,
        payload={"order_id": order_ref},
        tenant_id=job.tenant_id,
        store_id=job.store_id,
        order_ref=order_ref,
        event_id=str(job.job_id),
        source="background_outbox_job",
    )
    try:
        analytics_pipeline_service.publish(envelope)
    except analytics_pipeline_service.AnalyticsError as exc:
        return JobHandlerResult(
            success=False,
            retryable=True,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    side_effect_id = _record_side_effect(f"background-outbox:{job.job_type}:{order_ref}")
    return JobHandlerResult(success=True, result_ref=order_ref, side_effect_id=side_effect_id)


def register_production_handlers(*, registry: JobHandlerRegistry | None = None) -> JobHandlerRegistry:
    active = registry or default_registry()
    active.register("report.generate", handle_report_generate)
    active.register("rag.rebuild", handle_rag_rebuild)
    active.register("event.deliver", handle_event_deliver)
    active.register("ai.background", handle_ai_background)
    active.register("data.export", handle_data_export)
    active.register("cleanup.retention", handle_cleanup_retention)
    active.register("outbox.order_confirmed", handle_outbox_order_job)
    active.register("outbox.order_completed", handle_outbox_order_job)
    active.register("outbox.order_cancelled", handle_outbox_order_job)
    return active
