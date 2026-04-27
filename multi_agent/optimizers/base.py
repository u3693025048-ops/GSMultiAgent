#!/usr/bin/env python3
"""
Base Optimizer Abstract Class
Defines the interface for all optimization algorithms
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class OptimizationResult:
    """Result from an optimization run"""
    status: str  # "success" | "error" | "disabled"
    message: str = ""
    best_parameters: Dict[str, float] = field(default_factory=dict)
    best_fitness: float = 0.0
    objectives: Dict[str, float] = field(default_factory=dict)
    iterations: int = 0
    evaluations: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseOptimizer(ABC):
    """Abstract base class for all optimizers"""

    name: str = "base"

    @abstractmethod
    async def optimize(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> OptimizationResult:
        """
        Run optimization to find best parameters.

        Args:
            objectives: Objective specifications
                {
                    "objective_name": {
                        "type": "minimize" | "maximize",
                        "weight": float,
                        "target": float (optional)
                    }
                }
            constraints: Parameter constraints
                {
                    "param_name": {"min": float, "max": float}
                }
            initial_params: Initial parameters to start from
            max_iterations: Maximum optimization iterations

        Returns:
            OptimizationResult with best parameters found
        """
        pass

    def _compute_fitness(
        self,
        params: Dict[str, float],
        objectives: Dict[str, Any],
        objective_values: Dict[str, float],
    ) -> float:
        """Compute weighted fitness from objective values"""
        fitness = 0.0
        total_weight = 0.0

        for obj_name, obj_spec in objectives.items():
            value = objective_values.get(obj_name, 0.0)
            weight = obj_spec.get("weight", 1.0)
            obj_type = obj_spec.get("type", "minimize")
            target = obj_spec.get("target", 0.0)

            if obj_type == "minimize":
                score = weight * (1.0 / (1.0 + abs(value - target)))
            else:
                score = weight * (1.0 + abs(value - target))

            fitness += score
            total_weight += weight

        return fitness / total_weight if total_weight > 0 else 0.0

    def _clip_params(
        self,
        params: Dict[str, float],
        constraints: Dict[str, Any],
    ) -> Dict[str, float]:
        """Clip parameters to satisfy constraints"""
        clipped = params.copy()
        for param_name, param_value in clipped.items():
            if param_name in constraints:
                cons = constraints[param_name]
                min_val = cons.get("min", float("-inf"))
                max_val = cons.get("max", float("inf"))
                clipped[param_name] = max(min_val, min(max_val, param_value))
        return clipped
