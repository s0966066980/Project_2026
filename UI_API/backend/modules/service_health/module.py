"""Whether the four services the kiosk depends on are answering, and how fast.

Batch P1 narrows maintenance health to connection status, latency, observation
time and a safe error. Everything the old panel showed beyond that — database
topology, schema head, adapter coverage, log file inventories, alert backlogs —
told an operator about the inside of the system rather than whether a customer
can order right now.

A probe reports what it observed. It never guesses: a service that has not been
reached yet is `unknown`, not `down`, because acting on a fabricated outage is as
costly as missing a real one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

# The only services this panel reports on. Adding one is a product decision, so the
# list is here rather than assembled from whatever happens to be configured.
WATCHED_SERVICES: tuple[tuple[str, str], ...] = (
    ("ui_api", "UI API"),
    ("ollama", "Ollama 文字模型"),
    ("r1_omni", "R1-Omni 情緒模型"),
    ("rag_retrieval", "RAG 檢索 API"),
)

_OK = "ok"
_DEGRADED = "degraded"
_DOWN = "down"
_UNKNOWN = "unknown"
_NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class ServiceStatus:
    key: str
    label: str
    status: str
    latency_ms: int | None
    observed_at: str
    safe_error: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "observed_at": self.observed_at,
            "safe_error": self.safe_error,
        }


class ServiceProbe(Protocol):
    def probe(self, key: str) -> dict[str, Any]:
        """Return status, latency_ms, observed_at and safe_error for one service."""


class ServiceHealthModule:
    def __init__(self, *, probe: ServiceProbe, slow_ms: int = 2000):
        self._probe = probe
        self._slow_ms = max(1, int(slow_ms))

    def snapshot(self) -> list[ServiceStatus]:
        return [self._status(key, label) for key, label in WATCHED_SERVICES]

    def _status(self, key: str, label: str) -> ServiceStatus:
        try:
            observation = self._probe.probe(key) or {}
        except Exception as exc:
            # A probe that raises is a fact about the probe, not about the service,
            # so it is reported as unknown with the reason rather than as an outage.
            return ServiceStatus(
                key=key,
                label=label,
                status=_UNKNOWN,
                latency_ms=None,
                observed_at="",
                safe_error=str(exc)[:200],
            )

        latency = observation.get("latency_ms")
        latency_ms = None if latency is None else max(0, int(latency))
        status = str(observation.get("status") or _UNKNOWN)
        # Answering slowly is not the same as answering, and an operator watching a
        # kiosk stall needs to see that difference without reading the number.
        if status == _OK and latency_ms is not None and latency_ms >= self._slow_ms:
            status = _DEGRADED
        if status not in {_OK, _DEGRADED, _DOWN, _UNKNOWN, _NOT_CONFIGURED}:
            status = _UNKNOWN
        return ServiceStatus(
            key=key,
            label=label,
            status=status,
            latency_ms=latency_ms,
            observed_at=str(observation.get("observed_at") or ""),
            safe_error=str(observation.get("safe_error") or "")[:200],
        )
