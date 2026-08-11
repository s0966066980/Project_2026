"""Persistence port for the catalog capability.

The capability declares what it needs; the composition root binds an adapter.
Catalog therefore never imports a repository, which is what keeps a table with
one writer from acquiring a second one by import.
"""

from __future__ import annotations

from typing import Protocol

from models.commercial_scope import CommercialScope

from capabilities.catalog.contracts import CatalogItem


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
