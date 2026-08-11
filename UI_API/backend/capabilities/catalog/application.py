"""Catalog reads and changes, served through bound persistence ports."""

from __future__ import annotations

from models.commercial_scope import CommercialScope

from capabilities.catalog.contracts import CatalogAvailabilityState, CatalogItem
from capabilities.catalog.ports import CatalogAvailabilityPort, CatalogReadPort, CatalogWritePort

_read_port: CatalogReadPort | None = None
_write_port: CatalogWritePort | None = None
_availability_port: CatalogAvailabilityPort | None = None


def bind_read_port(port: CatalogReadPort | None) -> None:
    """Bind the read adapter. Called by the composition root and by tests."""

    global _read_port
    _read_port = port


def bind_write_port(port: CatalogWritePort | None) -> None:
    global _write_port
    _write_port = port


def bind_availability_port(port: CatalogAvailabilityPort | None) -> None:
    global _availability_port
    _availability_port = port


def _container():
    from bootstrap.container import get_container

    return get_container()


def _reads() -> CatalogReadPort:
    return _read_port if _read_port is not None else _container().catalog_read_port()


def _writes() -> CatalogWritePort:
    return _write_port if _write_port is not None else _container().catalog_write_port()


def _availability() -> CatalogAvailabilityPort:
    return _availability_port if _availability_port is not None else _container().catalog_availability_port()


def list_items(
    scope: CommercialScope | None = None,
    *,
    include_retired: bool = False,
    ensure_seed: bool = True,
) -> list[CatalogItem]:
    """Every item in scope, retired ones included only when asked for."""

    return _reads().list_items(scope, include_retired=include_retired, ensure_seed=ensure_seed)


def list_active_items(scope: CommercialScope | None = None) -> list[CatalogItem]:
    """The sellable catalog: what ordering, pricing and recommendation may use."""

    return list_items(scope, include_retired=False, ensure_seed=True)


def get_item(
    scope: CommercialScope,
    item_id: str,
    *,
    include_retired: bool = True,
) -> CatalogItem | None:
    return _reads().get_item(scope, item_id, include_retired=include_retired)


def create_item(scope: CommercialScope, payload: dict) -> CatalogItem:
    return _writes().create_item(scope, payload)


def update_item(scope: CommercialScope, item_id: str, payload: dict) -> CatalogItem:
    return _writes().update_item(scope, item_id, payload)


def retire_item(scope: CommercialScope, item_id: str) -> CatalogItem:
    """Soft-remove from the sellable catalog; history stays addressable."""

    return _writes().retire_item(scope, item_id)


def restore_item(scope: CommercialScope, item_id: str) -> CatalogItem:
    return _writes().restore_item(scope, item_id)


def upload_item_image(
    scope: CommercialScope,
    item_id: str,
    *,
    data: bytes,
    content_type: str,
    filename: str,
) -> CatalogItem:
    return _writes().upload_item_image(
        scope,
        item_id,
        data=data,
        content_type=content_type,
        filename=filename,
    )


def load_item_image(scope: CommercialScope, item_id: str) -> tuple[bytes, str]:
    return _writes().load_item_image(scope, item_id)


def replace_catalog(scope: CommercialScope, items: list) -> list[CatalogItem]:
    """Bulk replace the store's catalog. Still one writer, just a wider change."""

    return _writes().replace_catalog(scope, items)


def get_availability(scope: CommercialScope) -> CatalogAvailabilityState:
    return _availability().get_state(scope)


def save_availability(scope: CommercialScope, payload: dict) -> CatalogAvailabilityState:
    return _availability().save_state(scope, payload)
