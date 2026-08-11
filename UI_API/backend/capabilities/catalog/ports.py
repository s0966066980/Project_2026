"""Persistence ports for the catalog capability.

The capability declares what it needs; the composition root binds adapters.
Catalog therefore never imports a repository or a service, which is what keeps
a table with one writer from acquiring a second one by import.
"""

from __future__ import annotations

from typing import Protocol

from models.commercial_scope import CommercialScope

from capabilities.catalog.contracts import CatalogAvailabilityState, CatalogItem


class CatalogReadPort(Protocol):
    def list_items(
        self,
        scope: CommercialScope | None = None,
        *,
        include_retired: bool = False,
        ensure_seed: bool = True,
    ) -> list[CatalogItem]: ...

    def get_item(
        self,
        scope: CommercialScope,
        item_id: str,
        *,
        include_retired: bool = True,
    ) -> CatalogItem | None: ...


class CatalogWritePort(Protocol):
    """Every mutation of a catalog-owned table passes through here."""

    def create_item(self, scope: CommercialScope, payload: dict) -> CatalogItem: ...

    def update_item(self, scope: CommercialScope, item_id: str, payload: dict) -> CatalogItem: ...

    def retire_item(self, scope: CommercialScope, item_id: str) -> CatalogItem: ...

    def restore_item(self, scope: CommercialScope, item_id: str) -> CatalogItem: ...

    def upload_item_image(
        self,
        scope: CommercialScope,
        item_id: str,
        *,
        data: bytes,
        content_type: str,
        filename: str,
    ) -> CatalogItem: ...

    def load_item_image(self, scope: CommercialScope, item_id: str) -> tuple[bytes, str]: ...

    def replace_catalog(self, scope: CommercialScope, items: list) -> list[CatalogItem]: ...


class CatalogAvailabilityPort(Protocol):
    def get_state(self, scope: CommercialScope) -> CatalogAvailabilityState: ...

    def save_state(self, scope: CommercialScope, payload: dict) -> CatalogAvailabilityState: ...
