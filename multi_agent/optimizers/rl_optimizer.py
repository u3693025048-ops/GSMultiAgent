#!/usr/bin/env python3
"""
RL Optimizer
Optimization implementation using Reinforcement Learning
"""

import random
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseOptimizer, OptimizationResult
from .registry import OptimizerRegistry


@OptimizerRegistry.register("rl")
class RLOptimizer(BaseOptimizer):
    """
    Reinforcement Learning optimizer using Q-learning approach.
    """

    name = "reinforcement_learning"

    def __init__(
        self,
        algorithm: str = "q_learning",
        learning_rate: float = 0.01,
        discount_factor: float = 0.95,
        epsilon: float = 0.1,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.01,
        batch_size: int = 32,
        memory_size: int = 10000,
    ):
        self.algorithm = algorithm
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.batch_size = batch_size
        self.memory_size = memory_size

        self.q_table: Dict[str, Dict[str, float]] = {}
        self.action_space: List[str] = []
        self.param_names: List[str] = []

    async def optimize(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> OptimizationResult:
        """Run RL-based optimization"""
        constraints = constraints or {}
        initial_params = initial_params or {"x": 0.5}

        self.param_names = list(initial_params.keys())
        self._build_action_space(constraints)

        current_state = self._discretize_state(initial_params)
        self.q_table[current_state] = {action: 0.0 for action in self.action_space}

        best_params = initial_params.copy()
        best_fitness = float("-inf")
        history = []
        evaluations = 0

        for iteration in range(max_iterations):
            action = self._select_action(current_state)

            next_params = self._apply_action(best_params.copy(), action, constraints)

            fitness = await self._evaluate(next_params, objectives)
            evaluations += 1

            next_state = self._discretize_state(next_params)
            if next_state not in self.q_table:
                self.q_table[next_state] = {a: 0.0 for a in self.action_space}

            self._update_q_value(current_state, action, fitness, next_state)

            if fitness > best_fitness:
                best_fitness = fitness
                best_params = next_params.copy()

            history.append({
                "iteration": iteration,
                "best_fitness": best_fitness,
                "epsilon": self.epsilon,
                "best_params": best_params.copy(),
            })

            current_state = next_state
            self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        return OptimizationResult(
            status="success",
            message=f"RL optimization completed in {max_iterations} iterations",
            best_parameters=best_params,
            best_fitness=best_fitness,
            objectives=best_params,
            iterations=max_iterations,
            evaluations=evaluations,
            history=history,
            metadata={"optimizer": "reinforcement_learning", "algorithm": self.algorithm},
        )

    def _build_action_space(self, constraints: Dict[str, Any]) -> None:
        """Build discretized action space"""
        self.action_space = []
        step_sizes = [0.01, 0.05, 0.1, -0.01, -0.05, -0.1]

        for param_name in self.param_names:
            for step in step_sizes:
                self.action_space.append(f"{param_name}_{step}")

    def _discretize_state(self, params: Dict[str, float]) -> str:
        """Convert continuous params to discrete state string"""
        parts = []
        for name in sorted(self.param_names):
            val = params.get(name, 0.0)
            discrete_val = round(val, 2)
            parts.append(f"{name}={discrete_val}")
        return "|".join(parts)

    def _select_action(self, state: str) -> str:
        """Epsilon-greedy action selection"""
        if random.random() < self.epsilon:
            return random.choice(self.action_space)

        if state in self.q_table and self.q_table[state]:
            return max(self.q_table[state], key=self.q_table[state].get)
        return random.choice(self.action_space)

    def _apply_action(
        self,
        params: Dict[str, float],
        action: str,
        constraints: Dict[str, Any],
    ) -> Dict[str, float]:
        """Apply action to parameters"""
        param_name, step_str = action.rsplit("_", 1)
        step = float(step_str)

        new_params = params.copy()
        if param_name in new_params:
            new_params[param_name] += step

            if param_name in constraints:
                min_val = constraints[param_name].get("min", float("-inf"))
                max_val = constraints[param_name].get("max", float("inf"))
                new_params[param_name] = max(min_val, min(max_val, new_params[param_name]))

        return new_params

    async def _evaluate(
        self,
        params: Dict[str, float],
        objectives: Dict[str, Any],
    ) -> float:
        """Evaluate fitness for parameters"""
        return self._compute_fitness(params, objectives, params)

    def _update_q_value(
        self,
        state: str,
        action: str,
        reward: float,
        next_state: str,
    ) -> None:
        """Update Q-value using Q-learning update rule"""
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.action_space}

        max_next_q = 0.0
        if next_state in self.q_table and self.q_table[next_state]:
            max_next_q = max(self.q_table[next_state].values())

        current_q = self.q_table[state].get(action, 0.0)
        new_q = current_q + self.learning_rate * (reward + self.discount_factor * max_next_q - current_q)
        self.q_table[state][action] = new_q
