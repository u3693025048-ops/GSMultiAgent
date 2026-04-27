#!/usr/bin/env python3
"""
ParameterExperience (Dynamic Memory Buffer) Tools for Hermes Agent
Provides experience storage and retrieval capabilities
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ParameterExperienceToolMixin:
    """Mixin class to add ParameterExperience capabilities to tools"""

    def __init__(self, *args, **kwargs):
        self.parameter_experience = None
        super().__init__(*args, **kwargs)

    def set_parameter_experience(self, parameter_experience) -> None:
        """Set the ParameterExperience memory buffer"""
        self.parameter_experience = parameter_experience


class ParameterExperienceSearchTool(ParameterExperienceToolMixin):
    """Tool for retrieving similar experiences from ParameterExperience"""

    name = "parameter_experience_search"
    description = """
    Search for similar experiences in the dynamic memory buffer.
    Use this when you need to find historical cases with similar task context.
    Returns best matching experiences with fitness scores.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "object", "description": "Task context to search for"},
            "top_k": {
                "type": "integer",
                "description": "Number of similar experiences to retrieve",
                "default": 5,
            },
            "memory_type": {
                "type": "string",
                "description": "Type of memory: short_term, long_term, or all",
                "enum": ["short_term", "long_term", "all"],
                "default": "all",
            },
        },
        "required": ["query"],
    }

    async def execute(
        self, query: Dict[str, Any], top_k: int = 5, memory_type: str = "all"
    ) -> Dict[str, Any]:
        """Execute ParameterExperience search"""
        if not self.parameter_experience:
            return {"status": "error", "message": "ParameterExperience not initialized"}

        try:
            from ..memory.parameter_experience import MemoryType

            mem_type = None
            if memory_type == "short_term":
                mem_type = MemoryType.SHORT_TERM
            elif memory_type == "long_term":
                mem_type = MemoryType.LONG_TERM

            results = await self.parameter_experience.retrieve_similar(
                query=query, top_k=top_k, memory_type=mem_type
            )

            return {
                "status": "success",
                "query": query,
                "results_count": len(results),
                "experiences": results,
            }
        except Exception as e:
            logger.error(f"ParameterExperience search failed: {e}")
            return {"status": "error", "message": str(e)}


class ParameterExperienceStoreTool(ParameterExperienceToolMixin):
    """Tool for storing experiences in ParameterExperience"""

    name = "parameter_experience_store"
    description = """
    Store a new experience in the dynamic memory buffer.
    Use this after successful optimization to save best parameters and results.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "task_context": {"type": "object", "description": "Task context information"},
            "parameters": {"type": "object", "description": "Optimization parameters"},
            "objectives": {"type": "object", "description": "Objective values achieved"},
            "fitness": {"type": "number", "description": "Overall fitness score"},
            "memory_type": {
                "type": "string",
                "description": "short_term or long_term memory",
                "enum": ["short_term", "long_term"],
                "default": "short_term",
            },
        },
        "required": ["task_context", "parameters", "fitness"],
    }

    async def execute(
        self,
        task_context: Dict[str, Any],
        parameters: Dict[str, float],
        objectives: Dict[str, float],
        fitness: float,
        memory_type: str = "short_term",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute ParameterExperience store"""
        if not self.parameter_experience:
            return {"status": "error", "message": "ParameterExperience not initialized"}

        try:
            from ..memory.parameter_experience import MemoryType

            mem_type = MemoryType.LONG_TERM if memory_type == "long_term" else MemoryType.SHORT_TERM

            memory_id = await self.parameter_experience.store(
                task_context=task_context,
                parameters=parameters,
                objectives=objectives,
                fitness=fitness,
                memory_type=mem_type,
                metadata=metadata,
            )

            return {"status": "success", "memory_id": memory_id}
        except Exception as e:
            logger.error(f"ParameterExperience store failed: {e}")
            return {"status": "error", "message": str(e)}


class ParameterExperienceBestTool(ParameterExperienceToolMixin):
    """Tool for retrieving best performing experiences"""

    name = "parameter_experience_best"
    description = """
    Retrieve the best performing experiences for a given task context.
    Use this to leverage proven best solutions for similar tasks.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "task_context": {"type": "object", "description": "Task context to match against"},
            "top_k": {
                "type": "integer",
                "description": "Number of best experiences to retrieve",
                "default": 5,
            },
        },
        "required": ["task_context"],
    }

    async def execute(self, task_context: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
        """Execute ParameterExperience best retrieval"""
        if not self.parameter_experience:
            return {"status": "error", "message": "ParameterExperience not initialized"}

        try:
            results = await self.parameter_experience.retrieve_best(task_context=task_context, top_k=top_k)

            return {
                "status": "success",
                "task_context": task_context,
                "results_count": len(results),
                "best_experiences": results,
            }
        except Exception as e:
            logger.error(f"ParameterExperience best retrieval failed: {e}")
            return {"status": "error", "message": str(e)}


class ParameterExperienceStatsTool(ParameterExperienceToolMixin):
    """Tool for getting ParameterExperience statistics"""

    name = "parameter_experience_stats"
    description = """
    Get statistics about the dynamic memory buffer.
    Use this to understand memory usage and performance.
    """

    input_schema = {"type": "object", "properties": {}}

    async def execute(self) -> Dict[str, Any]:
        """Execute ParameterExperience stats"""
        if not self.parameter_experience:
            return {"status": "error", "message": "ParameterExperience not initialized"}

        try:
            stats = await self.parameter_experience.get_statistics()

            return {"status": "success", "statistics": stats}
        except Exception as e:
            logger.error(f"ParameterExperience stats failed: {e}")
            return {"status": "error", "message": str(e)}
