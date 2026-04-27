#!/usr/bin/env python3
"""
Genetic Optimizer
Optimization implementation using Genetic Algorithm
"""

import random
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseOptimizer, OptimizationResult
from .registry import OptimizerRegistry


@OptimizerRegistry.register("ga")
class GeneticOptimizer(BaseOptimizer):
    """
    Genetic Algorithm optimizer for multi-objective optimization.
    """

    name = "genetic_algorithm"

    def __init__(
        self,
        population_size: int = 50,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.1,
        max_generations: int = 100,
        tournament_size: int = 3,
        elite_size: int = 2,
    ):
        self.population_size = population_size
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.max_generations = max_generations
        self.tournament_size = tournament_size
        self.elite_size = elite_size

    async def optimize(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> OptimizationResult:
        """Run genetic algorithm optimization"""
        max_iterations = min(max_iterations, self.max_generations)
        constraints = constraints or {}

        param_names = list(initial_params.keys()) if initial_params else ["x"]
        param_bounds = self._get_param_bounds(param_names, constraints, initial_params)

        population = self._initialize_population(param_names, param_bounds)

        best_individual = None
        best_fitness = float("-inf")
        history = []
        evaluations = 0

        for generation in range(max_iterations):
            fitness_scores = []

            for individual in population:
                fitness = await self._evaluate(individual, objectives)
                fitness_scores.append((individual, fitness))
                evaluations += 1

            fitness_scores.sort(key=lambda x: x[1], reverse=True)

            current_best_ind, current_best_fitness = fitness_scores[0]
            if current_best_fitness > best_fitness:
                best_fitness = current_best_fitness
                best_individual = current_best_ind.copy()

            history.append({
                "generation": generation,
                "best_fitness": best_fitness,
                "avg_fitness": sum(f[1] for f in fitness_scores) / len(fitness_scores),
                "best_params": best_individual.copy(),
            })

            new_population = [
                ind for ind, _ in fitness_scores[:self.elite_size]
            ]

            while len(new_population) < self.population_size:
                parent1 = self._tournament_select(fitness_scores)
                parent2 = self._tournament_select(fitness_scores)

                if random.random() < self.crossover_rate:
                    child1, child2 = self._crossover(parent1, parent2)
                else:
                    child1, child2 = parent1.copy(), parent2.copy()

                child1 = self._mutate(child1, param_bounds)
                child2 = self._mutate(child2, param_bounds)

                new_population.append(child1)
                if len(new_population) < self.population_size:
                    new_population.append(child2)

            population = new_population

        best_objectives = await self._evaluate(best_individual, objectives)

        return OptimizationResult(
            status="success",
            message=f"GA completed in {max_iterations} generations",
            best_parameters=best_individual,
            best_fitness=best_fitness,
            objectives=best_objectives,
            iterations=max_iterations,
            evaluations=evaluations,
            history=history,
            metadata={"optimizer": "genetic_algorithm"},
        )

    def _get_param_bounds(
        self,
        param_names: List[str],
        constraints: Dict[str, Any],
        initial_params: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Tuple[float, float]]:
        """Get parameter bounds from constraints or defaults"""
        bounds = {}
        for name in param_names:
            if name in constraints:
                bounds[name] = (constraints[name].get("min", 0.0), constraints[name].get("max", 1.0))
            else:
                bounds[name] = (0.0, 1.0)
        return bounds

    def _initialize_population(
        self,
        param_names: List[str],
        param_bounds: Dict[str, Tuple[float, float]],
    ) -> List[Dict[str, float]]:
        """Initialize random population"""
        population = []
        for _ in range(self.population_size):
            individual = {
                name: random.uniform(bounds[0], bounds[1])
                for name, bounds in param_bounds.items()
            }
            population.append(individual)
        return population

    async def _evaluate(
        self,
        individual: Dict[str, float],
        objectives: Dict[str, Any],
    ) -> float:
        """Evaluate fitness for an individual"""
        return self._compute_fitness(individual, objectives, individual)

    def _tournament_select(
        self,
        fitness_scores: List[Tuple[Dict[str, float], float]],
    ) -> Dict[str, float]:
        """Tournament selection"""
        tournament = random.sample(fitness_scores, min(self.tournament_size, len(fitness_scores)))
        return max(tournament, key=lambda x: x[1])[0].copy()

    def _crossover(
        self,
        parent1: Dict[str, float],
        parent2: Dict[str, float],
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """Blend crossover operation"""
        child1, child2 = {}, {}
        alpha = 0.5
        for key in parent1:
            min_val = min(parent1[key], parent2[key])
            max_val = max(parent1[key], parent2[key])
            delta = max_val - min_val
            child1[key] = random.uniform(min_val - alpha * delta, max_val + alpha * delta)
            child2[key] = random.uniform(min_val - alpha * delta, max_val + alpha * delta)
        return child1, child2

    def _mutate(
        self,
        individual: Dict[str, float],
        param_bounds: Dict[str, Tuple[float, float]],
    ) -> Dict[str, float]:
        """Gaussian mutation"""
        mutated = individual.copy()
        for key in mutated:
            if random.random() < self.mutation_rate:
                min_val, max_val = param_bounds[key]
                sigma = (max_val - min_val) * 0.1
                mutated[key] += random.gauss(0, sigma)
                mutated[key] = max(min_val, min(max_val, mutated[key]))
        return mutated
