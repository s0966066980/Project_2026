"""Composition root for single-store local pilot adapters and applications."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from modules.runtime_persistence.runtime import current_profile


@dataclass(frozen=True)
class AdapterSelection:
    llm: str
    multimodal: str
    object_storage: str
    payment: str
    pos: str
    database: str


def resolve_adapter_selection() -> AdapterSelection:
    return AdapterSelection(
        llm=os.getenv("LLM_PORT", "ollama").strip().lower() or "ollama",
        multimodal=os.getenv("MULTIMODAL_PORT", "disabled").strip().lower() or "disabled",
        object_storage=os.getenv("OBJECT_STORAGE_PORT", "local").strip().lower() or "local",
        payment=os.getenv("PAYMENT_BACKEND", os.getenv("PAYMENT_PORT", "manual")).strip().lower() or "manual",
        pos=os.getenv("POS_BACKEND", os.getenv("POS_PORT", "manual")).strip().lower() or "manual",
        database=current_profile().backend,
    )


@lru_cache(maxsize=1)
def get_container() -> "AppContainer":
    return AppContainer(resolve_adapter_selection())


class AppContainer:
    """Lazy composition root. Modules should depend on ports, not this class, outside bootstrap."""

    def __init__(self, selection: AdapterSelection) -> None:
        self.selection = selection

    def payment_port(self):
        from integrations.payment.manual import ManualPaymentAdapter

        if self.selection.payment != "manual":
            # Single-store pilot only supports manual payment until certified.
            return ManualPaymentAdapter()
        return ManualPaymentAdapter()

    def pos_port(self):
        from integrations.pos.manual import ManualPOSAdapter

        return ManualPOSAdapter()

    def object_storage_port(self):
        from services import object_storage_service

        # Local disk / memory selected by existing OBJECT_STORAGE_BACKEND env.
        return object_storage_service.storage()

    def catalog_read_port(self):
        """Bind the catalog capability to the store menu tables it owns.

        The adapter lives here rather than inside `capabilities/catalog`
        because a capability that imports a repository has not stopped
        depending on the legacy layer, it has only moved the import.
        """

        return _LegacyMenuRepositoryCatalogAdapter()


class _LegacyMenuRepositoryCatalogAdapter:
    """Satisfies `CatalogReadPort` from the existing menu repository."""

    def list_items(self, scope=None, *, include_retired: bool = False, ensure_seed: bool = True):
        from repositories import menu_repository

        return menu_repository.get_menu_scoped(
            scope,
            include_retired=include_retired,
            ensure_seed=ensure_seed,
        )

    def get_item(self, scope, item_id: str, *, include_retired: bool = True):
        from repositories import menu_repository

        return menu_repository.get_item_scoped(scope, item_id, include_retired=include_retired)
