#!/usr/bin/env python3
"""
NoOp Optimizer
Disabled optimizer that returns a neutral result
"""

from typing import Any, Dict, Optional

from .base import BaseOptimizer, OptimizationResult
from .registry import OptimizerRegistry


@OptimizerRegistry.register("noop")
class NoOpOptimizer(BaseOptimizer):
    """
    No-operation optimizer used when optimization is disabled.
    Returns a neutral result without performing any optimization.
    """

    name = "noop"

    async def optimize(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> OptimizationResult:
        """Return neutral result indicating optimizer is disabled"""
        return OptimizationResult(
            status="disabled",
            message="Optimizer is disabled in configuration",
            best_parameters=initial_params or {},
            best_fitness=0.0,
            objectives={},
            iterations=0,
            evaluations=0,
            history=[],
            metadata={"reason": "optimizer_disabled"},
        )
