#!/usr/bin/env python3
"""
Optimization and Simulation Tools for Hermes Agent
Provides multi-objective optimization and simulation capabilities
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class OptimizationTool:
    """Tool for multi-objective optimization using pluggable optimizer"""

    name = "optimize"
    description = """
    Run multi-objective optimization to find best parameters.
    Use this when you need to optimize design parameters like navigation coefficients,
    damping ratios, or control gains based on simulation results.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "objectives": {
                "type": "object",
                "description": "Objective specifications",
                "example": {
                    "miss_distance": {"type": "minimize", "weight": 1.0, "target": 0},
                    "control_energy": {"type": "minimize", "weight": 0.8, "target": 0},
                },
            },
            "constraints": {
                "type": "object",
                "description": "Parameter constraints",
                "example": {
                    "navigation_coefficient": {"min": 0.1, "max": 1.0},
                    "damping_ratio": {"min": 0.0, "max": 0.5},
                },
            },
            "initial_params": {"type": "object", "description": "Initial parameters to start from"},
            "max_iterations": {
                "type": "integer",
                "description": "Maximum optimization iterations",
                "default": 50,
            },
        },
        "required": ["objectives"],
    }

    def __init__(self, *args, **kwargs):
        self.optimizer = None
        self.parameter_experience = None
        self.rl_learner = None
        super().__init__(*args, **kwargs)

    def set_optimizer(self, optimizer) -> None:
        """Set the optimizer instance (supports any BaseOptimizer implementation)"""
        self.optimizer = optimizer

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience

    def set_rl_learner(self, rl_learner) -> None:
        self.rl_learner = rl_learner

    async def execute(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> Dict[str, Any]:
        """Execute optimization using the configured optimizer"""
        if not self.optimizer:
            return {"status": "error", "message": "Optimizer not initialized"}

        try:
            from ..agents.base_agent import AgentMessage

            message = AgentMessage(
                sender="hermes_tool",
                receiver="Optimizer",
                content={
                    "objectives": objectives,
                    "constraints": constraints or {},
                    "initial_params": initial_params or {},
                    "max_iterations": max_iterations,
                },
                message_type="optimize",
            )

            response = await self.optimizer.process_message(message)

            return {"status": "success", "result": response.content}
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            return {"status": "error", "message": str(e)}

    async def execute_direct(
        self,
        objectives: Dict[str, Any],
        constraints: Optional[Dict[str, Any]] = None,
        initial_params: Optional[Dict[str, float]] = None,
        max_iterations: int = 50,
    ) -> Dict[str, Any]:
        """
        Execute optimization directly using the optimizer instance.
        This method calls the optimizer's optimize method directly without
        going through message passing.
        """
        if not self.optimizer:
            return {"status": "error", "message": "Optimizer not initialized"}

        try:
            result = await self.optimizer.optimize(
                objectives=objectives,
                constraints=constraints,
                initial_params=initial_params,
                max_iterations=max_iterations,
            )

            return {
                "status": result.status,
                "message": result.message,
                "best_parameters": result.best_parameters,
                "best_fitness": result.best_fitness,
                "objectives": result.objectives,
                "iterations": result.iterations,
                "evaluations": result.evaluations,
                "history": result.history,
            }
        except Exception as e:
            logger.error(f"Optimization failed: {e}")
            return {"status": "error", "message": str(e)}


class SimulationTool:
    """Tool for running simulations"""

    name = "simulate"
    description = """
    Run a simulation with given parameters.
    Use this to evaluate design performance before optimization.
    Returns metrics like miss distance, control energy, and trajectory.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "parameters": {
                "type": "object",
                "description": "Simulation parameters",
                "example": {
                    "navigation_coefficient": 0.5,
                    "damping_ratio": 0.3,
                    "target": [10.0, 0.0],
                },
            },
            "duration": {"type": "number", "description": "Simulation duration", "default": 100.0},
            "dt": {"type": "number", "description": "Time step", "default": 0.01},
        },
        "required": ["parameters"],
    }

    def __init__(self, *args, **kwargs):
        self.simulator = None
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    async def execute(
        self, parameters: Dict[str, float], duration: float = 100.0, dt: float = 0.01
    ) -> Dict[str, Any]:
        """Execute simulation"""
        if not self.simulator:
            return {"status": "error", "message": "Simulator not initialized"}

        try:
            from ..agents.base_agent import AgentMessage

            message = AgentMessage(
                sender="hermes_tool",
                receiver="Simulation",
                content={"parameters": parameters, "duration": duration, "dt": dt},
                message_type="simulate",
            )

            response = await self.simulator.process_message(message)

            return {"status": "success", "result": response.content}
        except Exception as e:
            logger.error(f"Simulation failed: {e}")
            return {"status": "error", "message": str(e)}


class OptimizationWithSimulationTool:
    """Tool for complete optimization loop with simulation"""

    name = "optimize_with_simulation"
    description = """
    Run the complete optimization loop: simulate -> evaluate -> optimize -> repeat.
    This is the main tool for automated parameter optimization with real-time feedback.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Task description for the optimization"},
            "initial_params": {"type": "object", "description": "Initial parameters"},
            "objectives": {"type": "object", "description": "Optimization objectives"},
            "constraints": {"type": "object", "description": "Parameter constraints"},
            "max_iterations": {
                "type": "integer",
                "description": "Maximum optimization iterations",
                "default": 30,
            },
        },
        "required": ["task", "objectives"],
    }

    def __init__(self, *args, **kwargs):
        self.orchestrator = None
        super().__init__(*args, **kwargs)

    def set_orchestrator(self, orchestrator) -> None:
        self.orchestrator = orchestrator

    async def execute(
        self,
        task: str,
        objectives: Dict[str, Any],
        initial_params: Optional[Dict[str, float]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        max_iterations: int = 30,
    ) -> Dict[str, Any]:
        """Execute optimization with simulation"""
        if not self.orchestrator:
            return {"status": "error", "message": "Orchestrator not initialized"}

        try:
            result = await self.orchestrator.submit_task(
                task={
                    "query": task,
                    "parameters": initial_params or {},
                    "objectives": objectives,
                    "constraints": constraints or {},
                },
                task_type="optimization",
                wait_for_result=True,
                timeout=max_iterations * 10.0,
            )

            return result
        except Exception as e:
            logger.error(f"Optimization with simulation failed: {e}")
            return {"status": "error", "message": str(e)}
