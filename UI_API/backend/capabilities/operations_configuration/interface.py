"""Published read-only Operations boundary.

Adapters remain bound by the composition root; callers do not import health or
settings repositories directly.
"""

from __future__ import annotations

from typing import Any, cast

from capabilities.operations_configuration.contracts import OperationsCapabilityError, ReadinessSnapshot


class _ObservabilityServiceProxy:
    """Keep runtime metric writes behind the Operations published surface."""

    def __getattr__(self, name: str):
        from services import observability_service

        return getattr(observability_service, name)


observability_service = _ObservabilityServiceProxy()


class _WorkerServiceProxy:
    """Expose durable background-job submission without a route-level import."""

    def __getattr__(self, name: str):
        from services import worker_service

        return getattr(worker_service, name)


worker_service = _WorkerServiceProxy()


def build_metadata() -> dict[str, str]:
    """What this running build is, for an operator standing in front of the device.

    Every field is a property of the build or its configuration; none is a
    secret, and none reads the database. `schema_version` is the migration head
    the build carries, not the head the database is at — those differ exactly
    when a deployment is half-applied, which is when the difference matters.
    """

    import config
    from modules.runtime_persistence.migrations import local_schema_head

    return {
        "version": config.APP_VERSION,
        "git_sha": config.APP_GIT_REVISION or "unknown",
        "build_time": config.APP_BUILD_TIME or "unknown",
        "schema_version": local_schema_head() or "unknown",
        "deployment_profile": config.APP_ENV,
    }


def readiness_snapshot() -> ReadinessSnapshot:
    from services import health_service

    return cast(ReadinessSnapshot, health_service.build_readiness())


def operations_overview(*, scope: Any, days: int = 30) -> dict[str, Any]:
    from modules.operations_overview import runtime

    return (
        runtime.default_module()
        .build(
            scope=scope,
            since=runtime.since_days_ago(days=max(1, min(int(days), 31))),
        )
        .as_dict()
    )


def service_health_runtime() -> Any:
    """Return the service-health application adapter without leaking its module."""

    from modules.service_health import runtime

    return runtime


def get_public_settings(scope: Any) -> dict[str, Any]:
    from repositories import commercial_settings_repository

    return commercial_settings_repository.get_settings_scoped(scope)


def list_settings_versions(scope: Any, limit: int = 25) -> list[dict[str, Any]]:
    from repositories import commercial_settings_repository

    return commercial_settings_repository.list_versions_scoped(scope, limit)


def get_settings_version(scope: Any, version: int) -> dict[str, Any] | None:
    from repositories import commercial_settings_repository

    return commercial_settings_repository.get_version_settings(scope, version)


def save_settings(settings: dict[str, Any], scope: Any, *, actor_id: Any) -> dict[str, Any]:
    from repositories import commercial_settings_repository

    return commercial_settings_repository.save_settings_scoped(settings, scope, actor_id=actor_id)


def llm_readiness() -> dict[str, Any]:
    from services import llm_routing_service

    return llm_routing_service.readiness()


def llm_connectivity_test() -> dict[str, Any]:
    from services import llm_routing_service

    return llm_routing_service.connectivity_test()


def llm_traffic_metrics() -> dict[str, Any]:
    from services import observability_service

    return observability_service.metrics_snapshot().get("llm_provider_requests_total", {})


def list_admin_audits(limit: int, scope: Any) -> list[dict[str, Any]]:
    from services import admin_audit_service

    return admin_audit_service.list_admin_audits(limit, scope)


async def build_admin_health(actions: list[dict[str, Any]]) -> dict[str, Any]:
    from services import health_service

    return await health_service.build_admin_health(actions)


def record_admin_action(*args: Any, **kwargs: Any) -> Any:
    from services import admin_audit_service

    return admin_audit_service.record_admin_action(*args, **kwargs)


def clear_session_logs() -> Any:
    from repositories import log_repository

    return log_repository.clear_session_logs()


def get_session_logs() -> list[dict[str, Any]]:
    from repositories import log_repository

    return log_repository.get_session_logs()


def delete_session_log(log_index: int) -> Any:
    from repositories import log_repository

    return log_repository.delete_session_log(log_index)


def compute_session_stats(logs: list[dict[str, Any]]) -> dict[str, Any]:
    from services import stats_service

    return stats_service.compute_session_stats(logs)


def operations_overview_runtime() -> Any:
    """Return the operations overview adapter for legacy DTO composition."""

    from modules.operations_overview import runtime

    return runtime


__all__ = [
    "OperationsCapabilityError",
    "ReadinessSnapshot",
    "operations_overview",
    "operations_overview_runtime",
    "get_public_settings",
    "list_settings_versions",
    "get_settings_version",
    "save_settings",
    "llm_readiness",
    "llm_connectivity_test",
    "llm_traffic_metrics",
    "list_admin_audits",
    "build_admin_health",
    "record_admin_action",
    "clear_session_logs",
    "get_session_logs",
    "delete_session_log",
    "compute_session_stats",
    "readiness_snapshot",
    "build_metadata",
    "service_health_runtime",
    "observability_service",
    "worker_service",
]
