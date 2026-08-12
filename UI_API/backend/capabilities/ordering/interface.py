"""Ordering deep-module surface; callers cannot write transaction tables directly."""

from modules.cart import CartError, CartModule
from modules.checkout_confirmation import CheckoutConfirmationModule, CheckoutError
from modules.checkout_confirmation import runtime as checkout_runtime
from modules.ordering_entry import EntryFlowError, OrderingEntryFlowModule, transition
from modules.ordering_entry import runtime as ordering_entry_runtime


class _CheckoutPricingServiceProxy:
    def __getattr__(self, name: str):
        from services import checkout_pricing_service

        return getattr(checkout_pricing_service, name)


checkout_pricing_service = _CheckoutPricingServiceProxy()


class _CheckoutOrderRepositoryProxy:
    def __getattr__(self, name: str):
        from repositories import checkout_order_repository

        return getattr(checkout_order_repository, name)


checkout_order_repository = _CheckoutOrderRepositoryProxy()

__all__ = [
    "CartError",
    "CartModule",
    "CheckoutConfirmationModule",
    "CheckoutError",
    "EntryFlowError",
    "OrderingEntryFlowModule",
    "checkout_runtime",
    "ordering_entry_runtime",
    "checkout_pricing_service",
    "checkout_order_repository",
    "transition",
]
