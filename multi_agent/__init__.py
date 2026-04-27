#!/usr/bin/env python3
"""
Multi-Agent Architecture
基于 Hermes Agent + RAG + ParameterExperience + RL + Simulation 的多智能体系统

核心设计理念：
- 使用 Hermes Agent 作为 LLM 编排引擎
- 我们的模块 (RAG/ParameterExperience/RL/Simulation) 作为 Hermes Tools 扩展
- 不重复实现 Agent 框架，专注垂直领域能力
"""

__version__ = "0.3.0"

import logging
import warnings
warnings.filterwarnings("ignore", message="Could not import tool module")
logging.getLogger("model_tools").setLevel(logging.ERROR)

# Memory
from .memory.parameter_experience import ParameterExperience, MemoryType
from .memory.rag_knowledge_base import RAGKnowledgeBase, EmbeddingConfig

# RL (internal RL module)
from .rl.reinforcement_learner import ReinforcementLearner, RLConfig as RLModuleConfig, RLAlgorithm
from .rl.experience_buffer import ExperienceBuffer

# Simulation
from .simulation import (
    GuidanceSimulator,
    GuidanceParameters,
    SimulationResult,
    SysMLModelGenerator,
    MATLABScriptGenerator,
    SimulationExecutor,
    GuidanceOptimizationWorkflow,
    OptimizationObjectives,
)

# Integration
from .integration import (
    HermesIntegration,
    HERMES_AVAILABLE,
    SubagentManager,
    SubagentConfig,
    SubagentResult,
    parallel_optimization,
    grid_search,
    IntelligentTaskPlanner,
    TaskPlan,
    ExecutionStrategy,
    smart_execute,
)

# Configuration (unified from config_loader.py)
from .config_loader import (
    load_config,
    get_config,
    reload_config,
    AppConfig,
    LLMConfig,
    ParameterExperienceConfig,
    RAGConfig,
    GAConfig,
    OptimizerConfig,
    OptimizerRLConfig,
)

# Optimizers (pluggable)
from .optimizers import (
    BaseOptimizer,
    OptimizationResult,
    OptimizerRegistry,
    OptimizerFactory,
    NoOpOptimizer,
    GeneticOptimizer,
    RLOptimizer,
)

# Tools
from .tools import (
    RAGRetrievalTool,
    RAGIndexTool,
    ParameterExperienceSearchTool,
    ParameterExperienceStoreTool,
    GenerateSysMLTool,
    GenerateMATLABTool,
    RunSimulationTool,
    ParameterStudyTool,
    OptimizeParametersTool,
    MemorySearchTool,
    MemoryStoreTool,
    OptimizationTool,
)

__all__ = [
    "__version__",
    # Memory
    "ParameterExperience",
    "MemoryType",
    "RAGKnowledgeBase",
    "EmbeddingConfig",
    # Simulation
    "GuidanceSimulator",
    "GuidanceParameters",
    "SimulationResult",
    "SysMLModelGenerator",
    "MATLABScriptGenerator",
    "SimulationExecutor",
    "GuidanceOptimizationWorkflow",
    "OptimizationObjectives",
    # RL
    "ReinforcementLearner",
    "RLModuleConfig",
    "RLAlgorithm",
    "ExperienceBuffer",
    # Integration
    "HermesIntegration",
    "HERMES_AVAILABLE",
    "SubagentManager",
    "SubagentConfig",
    "SubagentResult",
    "parallel_optimization",
    "grid_search",
    "IntelligentTaskPlanner",
    "TaskPlan",
    "ExecutionStrategy",
    "smart_execute",
    # Config
    "load_config",
    "get_config",
    "reload_config",
    "AppConfig",
    "LLMConfig",
    "ParameterExperienceConfig",
    "RAGConfig",
    "GAConfig",
    "OptimizerConfig",
    "OptimizerRLConfig",
    # Optimizers
    "BaseOptimizer",
    "OptimizationResult",
    "OptimizerRegistry",
    "OptimizerFactory",
    "NoOpOptimizer",
    "GeneticOptimizer",
    "RLOptimizer",
    # Tools
    "RAGRetrievalTool",
    "RAGIndexTool",
    "ParameterExperienceSearchTool",
    "ParameterExperienceStoreTool",
    "GenerateSysMLTool",
    "GenerateMATLABTool",
    "RunSimulationTool",
    "ParameterStudyTool",
    "OptimizeParametersTool",
    "MemorySearchTool",
    "MemoryStoreTool",
    "OptimizationTool",
]
