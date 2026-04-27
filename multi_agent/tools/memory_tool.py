#!/usr/bin/env python3
"""
Memory Tools for Hermes Agent
Provides unified memory search and storage across RAG and ParameterExperience
"""

import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class MemoryToolMixin:
    """Mixin for memory-related tools"""

    def __init__(self, *args, **kwargs):
        self.rag_kb = None
        self.parameter_experience = None
        super().__init__(*args, **kwargs)

    def set_rag_kb(self, rag_kb) -> None:
        self.rag_kb = rag_kb

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience


class MemorySearchTool(MemoryToolMixin):
    """Tool for unified memory search across RAG and ParameterExperience"""

    name = "memory_search"
    description = """
    Search across both knowledge base (RAG) and experience memory (ParameterExperience).
    Use this as the primary memory search tool for any query.
    Returns both documented knowledge and experiential learnings.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "search_type": {
                "type": "string",
                "description": "Type of search: all, knowledge, experience",
                "enum": ["all", "knowledge", "experience"],
                "default": "all",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results per source",
                "default": 3,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, search_type: str = "all", top_k: int = 3) -> Dict[str, Any]:
        """Execute unified memory search"""
        results = {
            "status": "success",
            "query": query,
            "knowledge_results": [],
            "experience_results": [],
        }

        try:
            if search_type in ["all", "knowledge"] and self.rag_kb:
                rag_results = await self.rag_kb.retrieve(query=query, top_k=top_k)
                results["knowledge_results"] = rag_results

            if search_type in ["all", "experience"] and self.parameter_experience:
                exp_results = await self.parameter_experience.retrieve_similar(query={"query": query}, top_k=top_k)
                results["experience_results"] = exp_results

            return results
        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return {"status": "error", "message": str(e)}


class MemoryStoreTool(MemoryToolMixin):
    """Tool for storing to both RAG and ParameterExperience"""

    name = "memory_store"
    description = """
    Store information to memory.
    Use 'knowledge' type for documented information to be retrieved via search.
    Use 'experience' type for optimization results and learnings.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Content to store"},
            "metadata": {"type": "object", "description": "Additional metadata"},
            "memory_type": {
                "type": "string",
                "description": "Type: knowledge or experience",
                "enum": ["knowledge", "experience"],
            },
        },
        "required": ["content", "memory_type"],
    }

    async def execute(
        self, content: str, memory_type: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute memory store"""
        try:
            if memory_type == "knowledge":
                if not self.rag_kb:
                    return {"status": "error", "message": "RAG not initialized"}

                await self.rag_kb.index_documents(
                    [{"content": content, "metadata": metadata or {}}]
                )
                return {"status": "success", "message": "Stored to knowledge base"}

            elif memory_type == "experience":
                if not self.parameter_experience:
                    return {"status": "error", "message": "ParameterExperience not initialized"}

                memory_id = await self.parameter_experience.store(
                    task_context=metadata or {},
                    parameters=metadata.get("parameters", {}) if metadata else {},
                    objectives=metadata.get("objectives", {}) if metadata else {},
                    fitness=metadata.get("fitness", 0.0) if metadata else 0.0,
                    memory_type=None,
                )
                return {"status": "success", "memory_id": memory_id}

            return {"status": "error", "message": f"Unknown memory type: {memory_type}"}
        except Exception as e:
            logger.error(f"Memory store failed: {e}")
            return {"status": "error", "message": str(e)}


class MemoryStatsTool(MemoryToolMixin):
    """Tool for getting memory statistics"""

    name = "memory_stats"
    description = """
    Get statistics about memory usage.
    Returns counts and utilization for both knowledge and experience memory.
    """

    input_schema = {"type": "object", "properties": {}}

    async def execute(self) -> Dict[str, Any]:
        """Execute memory stats"""
        results = {"status": "success"}

        try:
            if self.rag_kb:
                rag_stats = await self.rag_kb.get_statistics()
                results["knowledge_base"] = rag_stats

            if self.parameter_experience:
                parameter_experience_stats = await self.parameter_experience.get_statistics()
                results["experience_memory"] = parameter_experience_stats

            return results
        except Exception as e:
            logger.error(f"Memory stats failed: {e}")
            return {"status": "error", "message": str(e)}
