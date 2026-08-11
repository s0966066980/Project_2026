"""Published catalog contracts.

The rows are still the repository's dictionaries. Typing them is a behaviour
change for thirteen consumers that read differently shaped keys, so it belongs
to its own step — this one establishes ownership without moving semantics.
"""

from __future__ import annotations

from typing import Any

#: One sellable Store Menu Item as the catalog publishes it today.
CatalogItem = dict[str, Any]

#: The store's availability overlay: statuses, service period and the item rows
#: they apply to.
CatalogAvailabilityState = dict[str, Any]


class CatalogUnavailableError(RuntimeError):
    """Raised when the catalog cannot answer a read it is authoritative for."""


class CatalogWriteError(ValueError):
    """A refused catalog change, carrying the reason a caller can act on.

    The capability publishes its own error rather than leaking the service
    layer's, so a transport can map a code to a status without importing the
    implementation that produced it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
