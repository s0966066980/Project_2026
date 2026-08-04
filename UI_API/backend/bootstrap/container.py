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
