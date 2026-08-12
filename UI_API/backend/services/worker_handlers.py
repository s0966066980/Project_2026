"""Production background job handlers with observable side effects."""

from __future__ import annotations

from capabilities.knowledge_rag import knowledge_publication_runtime

from models.commercial_scope import CommercialScope
from models.worker_jobs import BackgroundJob, JobHandlerResult
from services import analytics_pipeline_service, observability_service
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


def handle_knowledge_publication_index(job: BackgroundJob) -> JobHandlerResult:
    attempt_id = str(job.payload_ref.get("attempt_id") or "").strip()
    if not attempt_id or job.store_id is None:
        return JobHandlerResult(
            success=False,
            retryable=False,
            safe_error="invalid_publication_attempt_reference",
        )
    try:
        result = knowledge_publication_runtime.default_module().run_attempt(
            scope=CommercialScope(job.tenant_id, job.store_id),
            attempt_id=attempt_id,
            actor="publication-worker",
            retry_budget_exhausted=job.attempt_count >= job.max_attempts,
        )
    except Exception as exc:
        return JobHandlerResult(
            success=False,
            retryable=job.attempt_count < job.max_attempts,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    if result["retryable"]:
        return JobHandlerResult(
            success=False,
            retryable=True,
            safe_error=str(result["status"]),
            result_ref=attempt_id,
        )
    if result["status"] != "published":
        return JobHandlerResult(
            success=False,
            retryable=False,
            safe_error=str(result["status"]),
            result_ref=attempt_id,
        )
    side_effect_id = _record_side_effect(f"knowledge-publication:{job.store_id}:{attempt_id}")
    return JobHandlerResult(
        success=True,
        result_ref=attempt_id,
        side_effect_id=side_effect_id,
    )


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


def _handle_push_copy_batch(job: BackgroundJob) -> JobHandlerResult:
    """逐項產生推薦詞並即時記錄進度。

    單一品項失敗不中止整批——一個模型逾時不該讓其餘一百多項的成果作廢；失敗數會留在批次紀錄裡
    讓操作者知道還有哪些要補。
    """

    from capabilities import catalog

    from repositories import push_copy_batch_repository, push_copy_repository
    from services import push_copy_authoring_service

    batch_id = str(job.payload_ref.get("batch_id") or "").strip()
    if not batch_id or job.store_id is None:
        return JobHandlerResult(success=False, retryable=False, safe_error="invalid_push_copy_batch_reference")

    scope = CommercialScope(job.tenant_id, job.store_id)
    batch = push_copy_batch_repository.get_batch(scope, batch_id)
    if batch is None:
        return JobHandlerResult(success=False, retryable=False, safe_error="push_copy_batch_not_found")

    push_copy_batch_repository.mark_running(scope, batch_id)
    menu_by_id = {str(row.get("id")): row for row in catalog.list_active_items() if row.get("id")}
    existing = push_copy_repository.list_copy_scoped(scope)

    for item_id in batch["item_ids"]:
        item = menu_by_id.get(item_id)
        if item is None:
            push_copy_batch_repository.record_item_result(scope, batch_id, ok=False, error=f"{item_id} 已不在菜單中")
            continue
        try:
            draft, error, _terms = push_copy_authoring_service.draft_copy(item, slot="base")
        except Exception as exc:  # noqa: BLE001 - 單項失敗不得讓整批崩潰
            push_copy_batch_repository.record_item_result(
                scope,
                batch_id,
                ok=False,
                error=observability_service.redact_sensitive_text(str(exc))[:200],
            )
            continue
        if error:
            push_copy_batch_repository.record_item_result(scope, batch_id, ok=False, error=error)
            continue
        entry = dict(existing.get(item_id) or {})
        entry["base_copy"] = draft
        push_copy_repository.save_copy_scoped(item_id, entry, scope, actor_id="push-copy-batch")
        push_copy_batch_repository.record_item_result(scope, batch_id, ok=True)

    final = push_copy_batch_repository.get_batch(scope, batch_id) or batch
    # 全數失敗才算整批失敗；只要有一筆成功就是有產出，操作者可以接手補剩下的。
    status = "failed" if final["succeeded"] == 0 and final["failed"] > 0 else "succeeded"
    push_copy_batch_repository.finish_batch(scope, batch_id, status=status)
    side_effect_id = _record_side_effect(f"push-copy-batch:{job.store_id}:{batch_id}")
    return JobHandlerResult(success=True, result_ref=batch_id, side_effect_id=side_effect_id)


def handle_ai_background(job: BackgroundJob) -> JobHandlerResult:
    if str(job.payload_ref.get("kind") or "").strip() == "push_copy_batch":
        return _handle_push_copy_batch(job)
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
    active.register("knowledge.publication.index", handle_knowledge_publication_index)
    active.register("event.deliver", handle_event_deliver)
    active.register("ai.background", handle_ai_background)
    active.register("data.export", handle_data_export)
    active.register("cleanup.retention", handle_cleanup_retention)
    active.register("outbox.order_confirmed", handle_outbox_order_job)
    active.register("outbox.order_completed", handle_outbox_order_job)
    active.register("outbox.order_cancelled", handle_outbox_order_job)
    return active
