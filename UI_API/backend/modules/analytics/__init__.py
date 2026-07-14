"""Analytics module public interface."""

from modules.analytics.application import (
    TouchValidationError,
    build_effectiveness_report,
    build_order_attributions,
    record_touch,
)
from modules.analytics.contracts import EffectivenessReport, TouchReceipt

__all__ = [
    "EffectivenessReport",
    "TouchReceipt",
    "TouchValidationError",
    "build_effectiveness_report",
    "build_order_attributions",
    "record_touch",
]
