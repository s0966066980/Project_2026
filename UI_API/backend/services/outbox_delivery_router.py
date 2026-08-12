"""Routes order outbox events to durable sinks with explicit ACK semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import UUID

from models.worker_jobs import OutboxDeliveryResult
from modules.analytics import _pipeline as analytics_pipeline_service
from modules.operations import _observability as observability_service

OutboxSink = Callable[[dict[str, Any]], OutboxDeliveryResult]

_ORDER_EVENT_TYPES = frozenset(
    {
        "order_confirmed",
        "order_completed",
        "order_cancelled",
    }
)


class OutboxDeliveryRouter:
    """Delivers outbox events only after a sink acknowledges durable receipt."""

    def __init__(self) -> None:
        self._sinks: dict[str, OutboxSink] = {}
        self._lock = Lock()

    def register(self, event_type: str, sink: OutboxSink) -> None:
        normalized = str(event_type or "").strip()
        if not normalized:
            raise ValueError("event_type is required")
        with self._lock:
            self._sinks[normalized] = sink

    def list_registered(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._sinks))

    def deliver(self, event: dict[str, Any]) -> OutboxDeliveryResult:
        event_type = str(event.get("event_type") or "").strip()
        if not event_type:
            observability_service.increment_metric("outbox_delivery_attempt", status="invalid_event")
            return OutboxDeliveryResult(success=False, retryable=False, safe_error="missing_event_type")
        with self._lock:
            sink = self._sinks.get(event_type)
        if sink is None:
            observability_service.increment_metric("outbox_delivery_attempt", status="unsupported_event_type")
            return OutboxDeliveryResult(
                success=False,
                retryable=False,
                safe_error=f"unsupported_outbox_event_type:{event_type}",
            )
        observability_service.increment_metric("outbox_delivery_attempt", status=event_type)
        try:
            result = sink(event)
        except Exception as exc:  # noqa: BLE001 - delivery boundary
            safe_error = observability_service.redact_sensitive_text(str(exc))[:200]
            observability_service.increment_metric("outbox_delivery_retry", status=event_type)
            return OutboxDeliveryResult(success=False, retryable=True, safe_error=safe_error)
        if result.success:
            observability_service.increment_metric(
                "outbox_delivery_success",
                status=result.provider or event_type,
            )
        elif result.retryable:
            observability_service.increment_metric("outbox_delivery_retry", status=event_type)
        else:
            observability_service.increment_metric("outbox_delivery_dlq", status=event_type)
        return result


_DEFAULT_ROUTER = OutboxDeliveryRouter()


def default_router() -> OutboxDeliveryRouter:
    return _DEFAULT_ROUTER


def _analytics_sink(event: dict[str, Any]) -> OutboxDeliveryResult:
    event_id = str(event.get("id") or "")
    event_type = str(event.get("event_type") or "")
    payload = dict(event.get("payload") or {})
    if not event_id or not event_type or not payload:
        return OutboxDeliveryResult(success=False, retryable=False, safe_error="invalid_outbox_event")
    tenant_id = event.get("tenant_id")
    if not isinstance(tenant_id, UUID):
        return OutboxDeliveryResult(success=False, retryable=False, safe_error="invalid_tenant_scope")
    store_id = event.get("store_id")
    store_uuid = store_id if isinstance(store_id, UUID) else None
    try:
        envelope = analytics_pipeline_service.build_envelope(
            event_type=event_type,
            payload=payload,
            tenant_id=tenant_id,
            store_id=store_uuid,
            order_ref=str(event.get("aggregate_id") or ""),
            event_id=event_id,
            source="order_outbox",
        )
        accepted = analytics_pipeline_service.publish(envelope)
    except analytics_pipeline_service.AnalyticsError as exc:
        return OutboxDeliveryResult(
            success=False,
            retryable=False,
            safe_error=observability_service.redact_sensitive_text(str(exc))[:200],
        )
    # Duplicate event_id is an idempotent ACK, not a failure.
    now = datetime.now(timezone.utc)
    if accepted or analytics_pipeline_service.event_already_persisted(event_id):
        return OutboxDeliveryResult(
            success=True,
            delivery_id=event_id,
            provider="analytics_json_sink",
            acknowledged_at=now,
        )
    return OutboxDeliveryResult(success=False, retryable=True, safe_error="analytics_sink_rejected")


def configure_default_outbox_router(*, router: OutboxDeliveryRouter | None = None) -> OutboxDeliveryRouter:
    active = router or default_router()
    for event_type in _ORDER_EVENT_TYPES:
        active.register(event_type, _analytics_sink)
    return active
