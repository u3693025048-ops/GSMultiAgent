#!/usr/bin/env python3
"""
Optimizer Registry
Registry pattern for pluggable optimizer implementations
"""

from typing import Any, Dict, Type

from .base import BaseOptimizer


class OptimizerRegistry:
    """Global registry for optimizer implementations"""

    _registry: Dict[str, Type[BaseOptimizer]] = {}

    @classmethod
    def register(cls, name: str):
        """
        Decorator to register an optimizer implementation.

        Usage:
            @OptimizerRegistry.register("ga")
            class GeneticOptimizer(BaseOptimizer):
                ...
        """
        def decorator(optimizer_cls: Type[BaseOptimizer]) -> Type[BaseOptimizer]:
            if not issubclass(optimizer_cls, BaseOptimizer):
                raise TypeError(
                    f"{optimizer_cls.__name__} must inherit from BaseOptimizer"
                )
            cls._registry[name] = optimizer_cls
            return optimizer_cls
        return decorator

    @classmethod
    def create(cls, name: str, config: Dict[str, Any] = None) -> BaseOptimizer:
        """
        Create an optimizer instance by name.

        Args:
            name: Registered optimizer name
            config: Configuration dict to pass to optimizer constructor

        Returns:
            Optimizer instance

        Raises:
            ValueError: If optimizer name is not registered
        """
        if name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"Unknown optimizer: '{name}'. Available: {available}"
            )

        optimizer_cls = cls._registry[name]
        if config:
            return optimizer_cls(**config)
        return optimizer_cls()

    @classmethod
    def get(cls, name: str) -> Type[BaseOptimizer]:
        """Get optimizer class by name"""
        return cls._registry.get(name)

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Check if an optimizer is registered"""
        return name in cls._registry

    @classmethod
    def list_optimizers(cls) -> list:
        """List all registered optimizer names"""
        return list(cls._registry.keys())
