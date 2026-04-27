#!/usr/bin/env python3
"""
Tools for Hermes Agent
"""

from .rag_tool import RAGRetrievalTool, RAGIndexTool
from .parameter_experience_tool import ParameterExperienceSearchTool, ParameterExperienceStoreTool, ParameterExperienceBestTool, ParameterExperienceStatsTool
from .simulation_tool import (
    GenerateSysMLTool,
    GenerateMATLABTool,
    RunSimulationTool,
    ParameterStudyTool,
    OptimizeParametersTool,
)
from .memory_tool import MemorySearchTool, MemoryStoreTool, MemoryStatsTool
from .optimization_tool import OptimizationTool
from .reflection_tool import ReflectionTool

__all__ = [
    # RAG Tools
    "RAGRetrievalTool",
    "RAGIndexTool",
    # ParameterExperience Tools
    "ParameterExperienceSearchTool",
    "ParameterExperienceStoreTool",
    "ParameterExperienceBestTool",
    "ParameterExperienceStatsTool",
    # Simulation Tools
    "GenerateSysMLTool",
    "GenerateMATLABTool",
    "RunSimulationTool",
    "ParameterStudyTool",
    "OptimizeParametersTool",
    # Memory Tools
    "MemorySearchTool",
    "MemoryStoreTool",
    "MemoryStatsTool",
    # Optimization Tools
    "OptimizationTool",
    # Reflection Tools
    "ReflectionTool",
]
