"""Connection status, latency and safe errors for the four services P1 watches."""

from .module import (
    WATCHED_SERVICES,
    ServiceHealthModule,
    ServiceProbe,
    ServiceStatus,
)

__all__ = [
    "WATCHED_SERVICES",
    "ServiceHealthModule",
    "ServiceProbe",
    "ServiceStatus",
]
