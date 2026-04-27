#!/usr/bin/env python3
"""
Hermes Agent Integration
"""

from .hermes_integration import HermesIntegration, HERMES_AVAILABLE
from .subagent import (
    SubagentManager,
    SubagentConfig,
    SubagentResult,
    parallel_optimization,
    grid_search,
)
from .task_planner import IntelligentTaskPlanner, TaskPlan, ExecutionStrategy, smart_execute

__all__ = [
    "HermesIntegration",
    "HERMES_AVAILABLE",
    # Subagent
    "SubagentManager",
    "SubagentConfig",
    "SubagentResult",
    "parallel_optimization",
    "grid_search",
    # Task Planner
    "IntelligentTaskPlanner",
    "TaskPlan",
    "ExecutionStrategy",
    "smart_execute",
]
