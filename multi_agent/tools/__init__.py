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
)
from .reflection_tool import ReflectionTool
from .matlab_rl_tool import MatlabRLOptimizationTool, ExtractMatlabParamsTool
from .syntax_check_tool import SyntaxCheckMATLABTool
from .judge_requirements_tool import JudgeRequirementsTool
from .memory_tools import (
    AgentMemoryRememberTool,
    AgentMemoryRecallTool,
    AgentMemoryListTool,
    AgentMemoryForgetTool,
)

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
    # Layer 2 New Tools
    "SyntaxCheckMATLABTool",
    "JudgeRequirementsTool",
    # Reflection Tools
    "ReflectionTool",
    # MATLAB RL Tools
    "MatlabRLOptimizationTool",
    "ExtractMatlabParamsTool",
    # Persistent Memory Tools
    "AgentMemoryRememberTool",
    "AgentMemoryRecallTool",
    "AgentMemoryListTool",
    "AgentMemoryForgetTool",
]
