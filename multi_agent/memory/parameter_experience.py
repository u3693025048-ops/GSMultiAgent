#!/usr/bin/env python3
"""
Dynamic Memory Buffer (Parameter Experience)
Implements trial-error-learning-reuse cycle
Supports short-term (current task) and long-term (validated best parameters) memory
"""

import logging
import time
import json
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import OrderedDict

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    EPISODIC = "episodic"


@dataclass
class MemoryEntry:
    memory_id: str
    memory_type: MemoryType
    task_context: Dict[str, Any]
    parameters: Dict[str, float]
    objectives: Dict[str, float]
    fitness: float
    timestamp: float = field(default_factory=time.time)
    access_count: int = 0
    last_access: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ParameterExperience:
    def __init__(
        self,
        max_short_term_size: int = 100,
        max_long_term_size: int = 1000,
        similarity_threshold: float = 0.7,
        decay_factor: float = 0.95,
        persist_path: str = "./parameter_experience_memory.json",
    ):
        self.max_short_term_size = max_short_term_size
        self.max_long_term_size = max_long_term_size
        self.similarity_threshold = similarity_threshold
        self.decay_factor = decay_factor
        self.persist_path = Path(persist_path)

        self._short_term_memory: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._long_term_memory: OrderedDict[str, MemoryEntry] = OrderedDict()
        self._episodic_memory: List[MemoryEntry] = []

        self._access_counts: Dict[str, int] = {}
        
        # Load persisted memory on initialization
        self.load()

    async def store(
        self,
        task_context: Dict[str, Any],
        parameters: Dict[str, float],
        objectives: Dict[str, float],
        fitness: float,
        metadata: Dict[str, Any] = None,
        memory_type: MemoryType = MemoryType.SHORT_TERM,
    ) -> str:
        """Store a new experience in memory"""
        memory_id = self._generate_memory_id(task_context, parameters)

        entry = MemoryEntry(
            memory_id=memory_id,
            memory_type=memory_type,
            task_context=task_context,
            parameters=parameters,
            objectives=objectives,
            fitness=fitness,
            metadata=metadata or {},
        )

        if memory_type == MemoryType.SHORT_TERM:
            self._short_term_memory[memory_id] = entry
            self._evict_short_term_if_needed()
        elif memory_type == MemoryType.LONG_TERM:
            self._long_term_memory[memory_id] = entry
            self._evict_long_term_if_needed()
        else:
            self._episodic_memory.append(entry)

        logger.info(f"Stored memory {memory_id} with fitness {fitness}")
        
        # Save memory state after store
        self.save()
        return memory_id

    async def retrieve_similar(
        self,
        query: Dict[str, Any],
        top_k: int = 5,
        memory_type: Optional[MemoryType] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve similar experiences based on task context"""
        results = []

        search_sources = []
        if memory_type is None:
            search_sources = [self._short_term_memory, self._long_term_memory]
        elif memory_type == MemoryType.SHORT_TERM:
            search_sources = [self._short_term_memory]
        elif memory_type == MemoryType.LONG_TERM:
            search_sources = [self._long_term_memory]
        elif memory_type == MemoryType.EPISODIC:
            search_sources = [self._episodic_memory]

        for memory_dict in search_sources:
            if isinstance(memory_dict, list):
                entries = memory_dict
            else:
                entries = list(memory_dict.values())

            scored_entries = []
            for entry in entries:
                similarity = self._compute_similarity(query, entry.task_context)
                if similarity >= self.similarity_threshold:
                    decayed_fitness = entry.fitness * (
                        self.decay_factor**entry.access_count
                    )
                    scored_entries.append((entry, similarity, decayed_fitness))

            scored_entries.sort(key=lambda x: (x[1] * x[2]), reverse=True)

            for entry, similarity, decayed_fitness in scored_entries[:top_k]:
                entry.access_count += 1
                entry.last_access = time.time()
                results.append(
                    {
                        "memory_id": entry.memory_id,
                        "parameters": entry.parameters,
                        "objectives": entry.objectives,
                        "fitness": decayed_fitness,
                        "original_fitness": entry.fitness,
                        "similarity": similarity,
                        "timestamp": entry.timestamp,
                        "memory_type": entry.memory_type.value,
                    }
                )

        return results

    async def retrieve_best(
        self,
        task_context: Dict[str, Any],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve best performing experiences"""
        all_entries = list(self._long_term_memory.values())

        scored_entries = []
        for entry in all_entries:
            similarity = self._compute_similarity(task_context, entry.task_context)
            score = entry.fitness * similarity
            scored_entries.append((entry, score))

        scored_entries.sort(key=lambda x: x[1], reverse=True)

        results = []
        for entry, score in scored_entries[:top_k]:
            entry.access_count += 1
            entry.last_access = time.time()
            results.append(
                {
                    "memory_id": entry.memory_id,
                    "parameters": entry.parameters,
                    "objectives": entry.objectives,
                    "fitness": entry.fitness,
                    "similarity": score,
                    "timestamp": entry.timestamp,
                }
            )

        return results

    async def promote_to_long_term(self, memory_id: str) -> bool:
        """Promote short-term memory to long-term"""
        if memory_id in self._short_term_memory:
            entry = self._short_term_memory.pop(memory_id)
            entry.memory_type = MemoryType.LONG_TERM
            self._long_term_memory[memory_id] = entry
            self._evict_long_term_if_needed()
            logger.info(f"Promoted memory {memory_id} to long-term")
            self.save()
            return True
        return False

    async def get_statistics(self) -> Dict[str, Any]:
        """Get memory buffer statistics"""
        short_term_avg_fitness = 0.0
        if self._short_term_memory:
            short_term_avg_fitness = sum(
                e.fitness for e in self._short_term_memory.values()
            ) / len(self._short_term_memory)

        long_term_avg_fitness = 0.0
        if self._long_term_memory:
            long_term_avg_fitness = sum(
                e.fitness for e in self._long_term_memory.values()
            ) / len(self._long_term_memory)

        return {
            "short_term_count": len(self._short_term_memory),
            "long_term_count": len(self._long_term_memory),
            "episodic_count": len(self._episodic_memory),
            "short_term_avg_fitness": short_term_avg_fitness,
            "long_term_avg_fitness": long_term_avg_fitness,
            "total_accesses": sum(self._access_counts.values()),
        }

    def _generate_memory_id(
        self, task_context: Dict[str, Any], parameters: Dict[str, float]
    ) -> str:
        """Generate unique memory ID"""
        content = json.dumps(
            {
                "context": task_context,
                "params": parameters,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _compute_similarity(
        self, query: Dict[str, Any], stored: Dict[str, Any]
    ) -> float:
        """Compute similarity between query and stored context"""
        if not query or not stored:
            return 0.0

        common_keys = set(query.keys()) & set(stored.keys())
        if not common_keys:
            return 0.0

        similarities = []
        for key in common_keys:
            q_val = query[key]
            s_val = stored[key]

            if isinstance(q_val, (int, float)) and isinstance(s_val, (int, float)):
                max_val = max(abs(q_val), abs(s_val), 1e-6)
                similarity = 1.0 - abs(q_val - s_val) / max_val
            elif isinstance(q_val, str) and isinstance(s_val, str):
                similarity = 1.0 if q_val == s_val else 0.0
            elif q_val == s_val:
                similarity = 1.0
            else:
                similarity = 0.0

            similarities.append(similarity)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _evict_short_term_if_needed(self) -> None:
        """Evict oldest short-term entries if capacity exceeded"""
        while len(self._short_term_memory) > self.max_short_term_size:
            self._short_term_memory.popitem(last=False)

    def _evict_long_term_if_needed(self) -> None:
        """Evict lowest fitness long-term entries if capacity exceeded"""
        while len(self._long_term_memory) > self.max_long_term_size:
            if not self._long_term_memory:
                break
            worst_id = min(
                self._long_term_memory.keys(),
                key=lambda mid: self._long_term_memory[mid].fitness,
            )
            self._long_term_memory.pop(worst_id)

    def clear(self, memory_type: Optional[MemoryType] = None) -> None:
        """Clear memory of specified type or all memory"""
        if memory_type is None:
            self._short_term_memory.clear()
            self._long_term_memory.clear()
            self._episodic_memory.clear()
            self._access_counts.clear()
        elif memory_type == MemoryType.SHORT_TERM:
            self._short_term_memory.clear()
        elif memory_type == MemoryType.LONG_TERM:
            self._long_term_memory.clear()
        elif memory_type == MemoryType.EPISODIC:
            self._episodic_memory.clear()
            
        # Always persist clear operations
        self.save()

    def save(self) -> bool:
        """Persist memory to disk"""
        try:
            # Ensure directory exists
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            
            def serialize_entry(entry: MemoryEntry) -> Dict:
                data = asdict(entry)
                data["memory_type"] = entry.memory_type.value
                return data
                
            data = {
                "short_term": [serialize_entry(e) for e in self._short_term_memory.values()],
                "long_term": [serialize_entry(e) for e in self._long_term_memory.values()],
                "episodic": [serialize_entry(e) for e in self._episodic_memory],
                "access_counts": self._access_counts
            }
            
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Successfully saved Parameter Experience memory to {self.persist_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save Parameter Experience memory to disk: {e}")
            return False

    def load(self) -> bool:
        """Load memory from disk"""
        if not self.persist_path.exists():
            return False
            
        try:
            with open(self.persist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            def deserialize_entry(entry_dict: Dict) -> MemoryEntry:
                entry_dict["memory_type"] = MemoryType(entry_dict["memory_type"])
                return MemoryEntry(**entry_dict)
                
            # Clear existing memory before loading
            self.clear()
            
            # Load short-term
            for item in data.get("short_term", []):
                entry = deserialize_entry(item)
                self._short_term_memory[entry.memory_id] = entry
                
            # Load long-term
            for item in data.get("long_term", []):
                entry = deserialize_entry(item)
                self._long_term_memory[entry.memory_id] = entry
                
            # Load episodic
            self._episodic_memory = [deserialize_entry(item) for item in data.get("episodic", [])]
            
            # Load access counts
            self._access_counts = data.get("access_counts", {})
            
            logger.info(f"Successfully loaded Parameter Experience memory from {self.persist_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load Parameter Experience memory from disk: {e}")
            return False
