"""Only published entrypoint for the reference-only Optimization Lab."""

from modules.optimization_lab import OptimizationLabError
from modules.optimization_lab import runtime as optimization_runtime

__all__ = ["OptimizationLabError", "optimization_runtime"]
