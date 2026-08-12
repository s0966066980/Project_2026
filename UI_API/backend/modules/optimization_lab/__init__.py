"""Store-scoped, reference-only Daily Optimization Simulation."""

from .contracts import (
    ANALYZER_DATA_SCOPES,
    EVIDENCE_LEVELS,
    FINDING_CLASSIFICATIONS,
    REPORT_SECTIONS,
    AnalyzerProfile,
    OptimizationLabError,
)
from .module import OptimizationLabModule

__all__ = [
    "ANALYZER_DATA_SCOPES",
    "AnalyzerProfile",
    "EVIDENCE_LEVELS",
    "FINDING_CLASSIFICATIONS",
    "OptimizationLabError",
    "OptimizationLabModule",
    "REPORT_SECTIONS",
]
