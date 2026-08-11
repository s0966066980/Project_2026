"""Catalog reads, served through a bound persistence port."""

from __future__ import annotations

from models.commercial_scope import CommercialScope

from capabilities.catalog.contracts import CatalogItem
from capabilities.catalog.ports import CatalogReadPort

_port: CatalogReadPort | None = None


def bind_read_port(port: CatalogReadPort | None) -> None:
    """Bind the persistence adapter. Called by the composition root and by tests."""

    global _port
    _port = port


def _resolve_port() -> CatalogReadPort:
    if _port is not None:
        return _port
    from bootstrap.container import get_container

    return get_container().catalog_read_port()


def list_items(
    scope: CommercialScope | None = None,
    *,
    include_retired: bool = False,
    ensure_seed: bool = True,
) -> list[CatalogItem]:
    """Every item in scope, retired ones included only when asked for."""

    return _resolve_port().list_items(scope, include_retired=include_retired, ensure_seed=ensure_seed)


def list_active_items(scope: CommercialScope | None = None) -> list[CatalogItem]:
    """The sellable catalog: what ordering, pricing and recommendation may use."""

    return list_items(scope, include_retired=False, ensure_seed=True)


def get_item(
    scope: CommercialScope,
    item_id: str,
    *,
    include_retired: bool = True,
) -> CatalogItem | None:
    return _resolve_port().get_item(scope, item_id, include_retired=include_retired)
