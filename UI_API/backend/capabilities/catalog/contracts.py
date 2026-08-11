"""Published catalog contracts.

The rows are still the repository's dictionaries. Typing them is a behaviour
change for thirteen consumers that read differently shaped keys, so it belongs
to its own step — this one establishes ownership without moving semantics.
"""

from __future__ import annotations

from typing import Any

#: One sellable Store Menu Item as the catalog publishes it today.
CatalogItem = dict[str, Any]


class CatalogUnavailableError(RuntimeError):
    """Raised when the catalog cannot answer a read it is authoritative for."""
