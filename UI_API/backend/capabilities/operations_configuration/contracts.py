"""Published operations/readiness vocabulary."""

from __future__ import annotations

from typing import Any, TypedDict


class ReadinessSnapshot(TypedDict, total=False):
    ready: bool
    status: str
    blocking: list[str]
    capabilities: dict[str, Any]


class OperationsCapabilityError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
