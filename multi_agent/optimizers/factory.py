#!/usr/bin/env python3
"""
Optimizer Factory
Factory for creating optimizer instances based on configuration
"""

from __future__ import annotations
from typing import Any, Dict, TYPE_CHECKING

from .base import BaseOptimizer
from .registry import OptimizerRegistry
from .noop_optimizer import NoOpOptimizer

if TYPE_CHECKING:
    from ..config_loader import GAConfig, OptimizerConfig, OptimizerRLConfig


class OptimizerFactory:
    """Factory for creating optimizer instances"""

    @staticmethod
    def create(config, ga_config=None, rl_config=None) -> BaseOptimizer:
        """
        Create an optimizer instance based on configuration.

        Args:
            config: Optimizer configuration (type, enabled)
            ga_config: Genetic algorithm configuration
            rl_config: Reinforcement learning configuration

        Returns:
            Optimizer instance (or NoOpOptimizer if disabled)
        """
        if not config.enabled:
            return NoOpOptimizer()

        optimizer_type = config.type

        if optimizer_type == "ga" and ga_config:
            optimizer_config = {
                "population_size": ga_config.population_size,
                "crossover_rate": ga_config.crossover_rate,
                "mutation_rate": ga_config.mutation_rate,
                "max_generations": ga_config.max_generations,
                "tournament_size": ga_config.tournament_size,
                "elite_size": ga_config.elite_size,
            }
        elif optimizer_type == "rl" and rl_config:
            optimizer_config = {
                "algorithm": rl_config.algorithm,
                "learning_rate": rl_config.learning_rate,
                "discount_factor": rl_config.discount_factor,
                "epsilon": rl_config.epsilon,
                "epsilon_decay": rl_config.epsilon_decay,
                "epsilon_min": rl_config.epsilon_min,
                "batch_size": rl_config.batch_size,
                "memory_size": rl_config.memory_size,
            }
        else:
            optimizer_config = {}

        return OptimizerRegistry.create(optimizer_type, optimizer_config)

    @staticmethod
    def create_from_dict(
        optimizer_type: str,
        optimizer_config: Dict[str, Any],
        enabled: bool = True,
    ) -> BaseOptimizer:
        """
        Create an optimizer instance from raw config dict.

        Args:
            optimizer_type: Type of optimizer ("ga", "rl", "noop")
            optimizer_config: Configuration dict for the optimizer
            enabled: Whether optimizer is enabled

        Returns:
            Optimizer instance
        """
        if not enabled:
            return NoOpOptimizer()

        return OptimizerRegistry.create(optimizer_type, optimizer_config)
