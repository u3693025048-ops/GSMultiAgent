#!/usr/bin/env python3
"""
Experience Buffer
Stores experiences for reinforcement learning
"""

import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Experience:
    state: List[float]
    action: List[float]
    reward: float
    next_state: Optional[List[float]]
    done: bool
    timestamp: float = field(default_factory=time.time)
    priority: float = 1.0
    trajectory_id: Optional[str] = None


class ExperienceBuffer:
    def __init__(
        self,
        capacity: int = 10000,
        batch_size: int = 32,
        priority_alpha: float = 0.6,
        priority_beta: float = 0.4,
    ):
        self.capacity = capacity
        self.batch_size = batch_size
        self.priority_alpha = priority_alpha
        self.priority_beta = priority_beta

        self._buffer: deque = deque(maxlen=capacity)
        self._priorities: deque = deque(maxlen=capacity)
        self._trajectories: Dict[str, List[int]] = {}

        self._total_reward = 0.0
        self._episode_count = 0

    def add(
        self,
        state: List[float],
        action: List[float],
        reward: float,
        next_state: Optional[List[float]],
        done: bool,
        trajectory_id: Optional[str] = None,
    ) -> None:
        """Add an experience to the buffer"""
        experience = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            done=done,
            trajectory_id=trajectory_id,
        )

        self._buffer.append(experience)

        priority = abs(reward) ** self.priority_alpha
        self._priorities.append(priority)

        if trajectory_id:
            if trajectory_id not in self._trajectories:
                self._trajectories[trajectory_id] = []
            self._trajectories[trajectory_id].append(len(self._buffer) - 1)

        self._total_reward += reward
        if done:
            self._episode_count += 1

    def sample(
        self, batch_size: Optional[int] = None
    ) -> Tuple[List[Experience], List[float]]:
        """Sample a batch of experiences"""
        if not self._buffer:
            return [], []

        batch_size = batch_size or self.batch_size
        batch_size = min(batch_size, len(self._buffer))

        priorities = np.array(list(self._priorities))
        probabilities = priorities / priorities.sum()

        indices = np.random.choice(
            len(self._buffer), size=batch_size, replace=False, p=probabilities
        )

        experiences = [self._buffer[i] for i in indices]
        weights = (len(self._buffer) * probabilities[indices]) ** (-self.priority_beta)
        weights = weights / weights.max()

        return experiences, weights.tolist()

    def get_trajectory(self, trajectory_id: str) -> List[Experience]:
        """Get all experiences for a trajectory"""
        if trajectory_id not in self._trajectories:
            return []

        indices = self._trajectories[trajectory_id]
        return [self._buffer[i] for i in indices if i < len(self._buffer)]

    def get_recent_experiences(self, n: int = 100) -> List[Dict[str, Any]]:
        """Get recent experiences"""
        recent = list(self._buffer)[-n:]
        return [
            {
                "state": exp.state,
                "action": exp.action,
                "reward": exp.reward,
                "done": exp.done,
            }
            for exp in recent
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get buffer statistics"""
        if not self._buffer:
            return {
                "size": 0,
                "capacity": self.capacity,
                "utilization": 0.0,
                "avg_reward": 0.0,
                "episode_count": 0,
            }

        rewards = [exp.reward for exp in self._buffer]

        return {
            "size": len(self._buffer),
            "capacity": self.capacity,
            "utilization": len(self._buffer) / self.capacity,
            "avg_reward": self._total_reward / len(self._buffer),
            "max_reward": max(rewards) if rewards else 0.0,
            "min_reward": min(rewards) if rewards else 0.0,
            "episode_count": self._episode_count,
            "trajectory_count": len(self._trajectories),
        }

    def clear(self) -> None:
        """Clear the buffer"""
        self._buffer.clear()
        self._priorities.clear()
        self._trajectories.clear()
        self._total_reward = 0.0
        self._episode_count = 0

    def update_priorities(self, indices: List[int], priorities: List[float]) -> None:
        """Update priorities for specific experiences"""
        for i, priority in zip(indices, priorities):
            if 0 <= i < len(self._priorities):
                self._priorities[i] = priority**self.priority_alpha

    def save(self, filepath: str) -> bool:
        """Save buffer to file"""
        try:
            data = {
                "experiences": [
                    {
                        "state": exp.state,
                        "action": exp.action,
                        "reward": exp.reward,
                        "next_state": exp.next_state,
                        "done": exp.done,
                        "trajectory_id": exp.trajectory_id,
                    }
                    for exp in self._buffer
                ],
                "priorities": list(self._priorities),
                "trajectories": self._trajectories,
                "stats": {
                    "total_reward": self._total_reward,
                    "episode_count": self._episode_count,
                },
            }

            import json

            with open(filepath, "w") as f:
                json.dump(data, f)

            return True
        except Exception as e:
            logger.error(f"Failed to save experience buffer: {e}")
            return False

    def load(self, filepath: str) -> bool:
        """Load buffer from file"""
        try:
            import json

            with open(filepath, "r") as f:
                data = json.load(f)

            self._buffer.clear()
            self._priorities.clear()

            for exp_data in data["experiences"]:
                exp = Experience(
                    state=exp_data["state"],
                    action=exp_data["action"],
                    reward=exp_data["reward"],
                    next_state=exp_data.get("next_state"),
                    done=exp_data.get("done", False),
                    trajectory_id=exp_data.get("trajectory_id"),
                )
                self._buffer.append(exp)

            self._priorities.extend(data.get("priorities", []))
            self._trajectories = data.get("trajectories", {})
            self._total_reward = data.get("stats", {}).get("total_reward", 0.0)
            self._episode_count = data.get("stats", {}).get("episode_count", 0)

            return True
        except Exception as e:
            logger.error(f"Failed to load experience buffer: {e}")
            return False
