#!/usr/bin/env python3
"""
memory_tools.py
Hermes-registry tool objects that expose HermesAgentMemory to the LLM.

Pattern follows hermes-agent-demo/agent.py — the three core memory operations
(remember, recall, list) plus forget are registered as first-class tools so
Hermes can persist findings (best parameters, design decisions, task outcomes)
across sessions automatically.

Each tool follows the GSMultiAgent13 tool class convention:
  • Class-level  .name, .description, .input_schema
  • Instance     .set_memory(mem)     — called by hermes_integration
  • Async        .execute(**kwargs)   — called by the Hermes registry dispatcher
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class _MemoryToolBase:
    """Common mixin: holds a reference to HermesAgentMemory and provides
    set_memory() so hermes_integration can inject it after construction."""

    def __init__(self) -> None:
        self._memory: Optional[Any] = None

    def set_memory(self, memory) -> None:
        self._memory = memory


class AgentMemoryRememberTool(_MemoryToolBase):
    """Save a piece of information to long-term persistent memory."""

    name = "agent_memory_remember"
    description = (
        "Save a piece of information to long-term persistent memory under a named key. "
        "The value is written to disk immediately and will be available in future sessions. "
        "Use this to remember important findings: best parameter sets, task outcomes, "
        "design decisions, notes about the guidance system, etc."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": (
                    "Short descriptive key, e.g. 'best_params_T2_iter3', "
                    "'design_decision_guidance_law', 'task_requirement_miss_5m'."
                ),
            },
            "value": {
                "type": "string",
                "description": "The information to store (string, JSON, free text).",
            },
        },
        "required": ["key", "value"],
    }

    async def execute(self, key: str, value: str) -> str:
        if self._memory is None:
            return json.dumps({"status": "error", "message": "Memory not initialized."})
        try:
            result = self._memory.remember(key, value)
            return json.dumps({"status": "success", "message": result})
        except Exception as exc:
            logger.error(f"[agent_memory_remember] {exc}")
            return json.dumps({"status": "error", "message": str(exc)})


class AgentMemoryRecallTool(_MemoryToolBase):
    """Retrieve a previously saved piece of information by its key."""

    name = "agent_memory_recall"
    description = (
        "Retrieve a value previously stored in long-term memory by its key. "
        "Returns the stored value and the timestamp it was saved."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The key used when the memory was saved.",
            },
        },
        "required": ["key"],
    }

    async def execute(self, key: str) -> str:
        if self._memory is None:
            return json.dumps({"status": "error", "message": "Memory not initialized."})
        try:
            result = self._memory.recall(key)
            return json.dumps({"status": "success", "message": result})
        except Exception as exc:
            logger.error(f"[agent_memory_recall] {exc}")
            return json.dumps({"status": "error", "message": str(exc)})


class AgentMemoryListTool(_MemoryToolBase):
    """List all keys currently stored in long-term memory."""

    name = "agent_memory_list"
    description = (
        "List all keys currently stored in long-term persistent memory, "
        "together with the timestamp each was saved. "
        "Useful for checking what the agent has remembered across sessions."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self) -> str:
        if self._memory is None:
            return json.dumps({"status": "error", "message": "Memory not initialized."})
        try:
            result = self._memory.list_memories()
            return json.dumps({"status": "success", "message": result})
        except Exception as exc:
            logger.error(f"[agent_memory_list] {exc}")
            return json.dumps({"status": "error", "message": str(exc)})


class AgentMemoryForgetTool(_MemoryToolBase):
    """Delete a stored memory entry by key."""

    name = "agent_memory_forget"
    description = (
        "Delete a specific entry from long-term persistent memory by its key. "
        "The change is persisted to disk immediately."
    )
    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "The key of the memory entry to delete.",
            },
        },
        "required": ["key"],
    }

    async def execute(self, key: str) -> str:
        if self._memory is None:
            return json.dumps({"status": "error", "message": "Memory not initialized."})
        try:
            result = self._memory.forget(key)
            return json.dumps({"status": "success", "message": result})
        except Exception as exc:
            logger.error(f"[agent_memory_forget] {exc}")
            return json.dumps({"status": "error", "message": str(exc)})
