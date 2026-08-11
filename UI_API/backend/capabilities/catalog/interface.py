"""The one surface other capabilities may use to read or change the store catalog.

Importing `repositories.menu_repository` or `services.menu_catalog_service`
from another capability puts a second owner on tables this capability owns;
going through here keeps the ownership statement true and gives the eventual
typed contract one place to land.
"""

from __future__ import annotations

from capabilities.catalog.application import (
    create_item,
    get_availability,
    get_item,
    list_active_items,
    list_items,
    load_item_image,
    restore_item,
    retire_item,
    save_availability,
    update_item,
    upload_item_image,
)
from capabilities.catalog.contracts import (
    CatalogAvailabilityState,
    CatalogItem,
    CatalogUnavailableError,
    CatalogWriteError,
)

__all__ = [
    "CatalogAvailabilityState",
    "CatalogItem",
    "CatalogUnavailableError",
    "CatalogWriteError",
    "create_item",
    "get_availability",
    "get_item",
    "list_active_items",
    "list_items",
    "load_item_image",
    "restore_item",
    "retire_item",
    "save_availability",
    "update_item",
    "upload_item_image",
]
