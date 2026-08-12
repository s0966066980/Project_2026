"""Registry for production background job handlers."""

from __future__ import annotations

from threading import Lock
from typing import Callable

from models.worker_jobs import ALLOWED_JOB_TYPES, BackgroundJob, JobHandlerResult, JobValidationError, validate_job_type

JobHandler = Callable[[BackgroundJob], JobHandlerResult]


class JobHandlerRegistry:
    """Maps job_type to a handler that must perform a real side effect before success."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._lock = Lock()

    def register(self, job_type: str, handler: JobHandler) -> None:
        normalized = validate_job_type(job_type)
        with self._lock:
            self._handlers[normalized] = handler

    def resolve(self, job_type: str) -> JobHandler | None:
        with self._lock:
            return self._handlers.get(str(job_type or "").strip())

    def list_registered(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._handlers))

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()

    def validate_required_handlers(self, required: frozenset[str] | None = None) -> None:
        required_types = required or ALLOWED_JOB_TYPES
        missing = sorted(required_types - set(self.list_registered()))
        if missing:
            raise JobValidationError(f"Missing required worker handlers: {', '.join(missing)}")


_DEFAULT_REGISTRY = JobHandlerRegistry()


def default_registry() -> JobHandlerRegistry:
    return _DEFAULT_REGISTRY
