"""The one surface other capabilities may use to read the store catalog.

Importing `repositories.menu_repository` from another capability puts a second
reader on a table this capability owns; going through here keeps the ownership
statement true and gives the eventual typed contract one place to land.
"""

from __future__ import annotations

from capabilities.catalog.application import get_item, list_active_items, list_items
from capabilities.catalog.contracts import CatalogItem, CatalogUnavailableError

__all__ = [
    "CatalogItem",
    "CatalogUnavailableError",
    "get_item",
    "list_active_items",
    "list_items",
]
