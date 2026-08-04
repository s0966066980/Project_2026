"""Recommendation module public interface."""

from modules.recommendation.application import STRATEGY_VERSION, decide, list_events

__all__ = ["STRATEGY_VERSION", "decide", "list_events"]
