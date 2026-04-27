#!/usr/bin/env python3
"""
RAG Tools for Hermes Agent
Provides knowledge retrieval and indexing capabilities
"""

import json
import logging
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolConfig:
    name: str
    description: str
    input_schema: Dict[str, Any]


class RAGToolMixin:
    """Mixin class to add RAG capabilities to tools"""

    def __init__(self, *args, **kwargs):
        self.rag_kb = None
        super().__init__(*args, **kwargs)

    def set_rag_kb(self, rag_kb) -> None:
        """Set the RAG knowledge base"""
        self.rag_kb = rag_kb


class RAGRetrievalTool(RAGToolMixin):
    """Tool for retrieving knowledge from RAG knowledge base"""

    name = "rag_retrieve"
    description = """
    Retrieve relevant knowledge from the knowledge base.
    Use this when user asks about domain knowledge, historical cases, or needs context augmentation.
    Returns relevant documents with relevance scores.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant knowledge",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum number of results to return",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Execute RAG retrieval"""
        if not self.rag_kb:
            return {"status": "error", "message": "RAG knowledge base not initialized"}

        try:
            results = await self.rag_kb.retrieve(query=query, top_k=top_k)

            return {
                "status": "success",
                "query": query,
                "results_count": len(results),
                "results": [
                    {
                        "content": r.get("content", "")[:500],
                        "score": r.get("score", 0.0),
                        "metadata": r.get("metadata", {}),
                    }
                    for r in results
                ],
            }
        except Exception as e:
            logger.error(f"RAG retrieval failed: {e}")
            return {"status": "error", "message": str(e)}


class RAGIndexTool(RAGToolMixin):
    """Tool for indexing documents into RAG knowledge base"""

    name = "rag_index"
    description = """
    Index new documents into the knowledge base.
    Use this when you need to add new knowledge or update existing documents.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "documents": {
                "type": "array",
                "description": "List of documents to index",
                "items": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}, "metadata": {"type": "object"}},
                },
            }
        },
        "required": ["documents"],
    }

    async def execute(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute RAG indexing"""
        if not self.rag_kb:
            return {"status": "error", "message": "RAG knowledge base not initialized"}

        try:
            count = await self.rag_kb.index_documents(documents=documents)

            return {"status": "success", "indexed_count": count}
        except Exception as e:
            logger.error(f"RAG indexing failed: {e}")
            return {"status": "error", "message": str(e)}


class SimilaritySearchTool(RAGToolMixin):
    """Tool for similarity search in knowledge base"""

    name = "rag_similarity_search"
    description = """
    Perform similarity search with a minimum threshold.
    Use this when you need to find highly similar documents.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "threshold": {
                "type": "number",
                "description": "Minimum similarity threshold (0-1)",
                "default": 0.7,
            },
            "top_k": {"type": "integer", "description": "Maximum number of results", "default": 10},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, threshold: float = 0.7, top_k: int = 10) -> Dict[str, Any]:
        """Execute similarity search"""
        if not self.rag_kb:
            return {"status": "error", "message": "RAG knowledge base not initialized"}

        try:
            results = await self.rag_kb.similarity_search(
                query=query, threshold=threshold, top_k=top_k
            )

            return {
                "status": "success",
                "query": query,
                "threshold": threshold,
                "results_count": len(results),
                "results": results,
            }
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return {"status": "error", "message": str(e)}
