"""Ordering deep-module surface; callers cannot write transaction tables directly."""

from modules.cart import CartError, CartModule
from modules.checkout_confirmation import CheckoutConfirmationModule, CheckoutError
from modules.checkout_confirmation import _pricing_service as checkout_pricing_service
from modules.checkout_confirmation import runtime as checkout_runtime
from modules.checkout_confirmation.adapters import orders as checkout_order_repository
from modules.ordering_entry import EntryFlowError, OrderingEntryFlowModule, transition
from modules.ordering_entry import runtime as ordering_entry_runtime

# Pricing and the order store used to be reached by call-time proxies into
# services/ and repositories/, which is what kept this capability — the one
# holding transaction authority — on the frozen legacy-layer list. They now
# live in modules/checkout_confirmation and are published directly.

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
