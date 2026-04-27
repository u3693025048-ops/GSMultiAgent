#!/usr/bin/env python3
"""
Reinforcement Learner
Implements RL algorithms for parameter optimization
"""

import logging
import time
import random
from typing import Any, Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import numpy as np

from .experience_buffer import ExperienceBuffer

logger = logging.getLogger(__name__)


class RLAlgorithm(Enum):
    Q_LEARNING = "q_learning"
    SARSA = "sarsa"
    DQN = "dqn"
    POLICY_GRADIENT = "policy_gradient"
    REINFORCE = "reinforce"


@dataclass
class RLConfig:
    algorithm: RLAlgorithm = RLAlgorithm.Q_LEARNING
    learning_rate: float = 0.01
    discount_factor: float = 0.95
    epsilon: float = 0.1
    epsilon_decay: float = 0.995
    epsilon_min: float = 0.01
    batch_size: int = 32
    target_update_freq: int = 100
    memory_capacity: int = 10000


class ReinforcementLearner:
    def __init__(self, config: RLConfig):
        self.config = config
        self.experience_buffer = ExperienceBuffer(
            capacity=config.memory_capacity, batch_size=config.batch_size
        )

        self._state_dim: int = 0
        self._action_dim: int = 0

        self._q_network: Optional[np.ndarray] = None
        self._target_network: Optional[np.ndarray] = None
        self._policy_network: Optional[np.ndarray] = None

        self._training_step = 0
        self._episode_rewards: List[float] = []
        self._current_episode_reward = 0.0

        self._epsilon = config.epsilon

    def initialize(self, state_dim: int, action_dim: int) -> None:
        """Initialize the RL learner with state and action dimensions"""
        self._state_dim = state_dim
        self._action_dim = action_dim

        hidden_dim = max(64, (state_dim + action_dim) // 2)

        self._q_network = (
            np.random.randn(state_dim, hidden_dim).astype(np.float32) * 0.01
        )
        self._q_network_b = np.zeros(hidden_dim, dtype=np.float32)
        self._q_network_2 = (
            np.random.randn(hidden_dim, action_dim).astype(np.float32) * 0.01
        )
        self._q_network_2_b = np.zeros(action_dim, dtype=np.float32)

        self._target_network = self._q_network.copy()
        self._target_b = self._q_network_b.copy()
        self._target_network_2 = self._q_network_2.copy()
        self._target_network_2_b = self._q_network_2_b.copy()

        self._policy_network = (
            np.random.randn(state_dim, hidden_dim).astype(np.float32) * 0.01
        )
        self._policy_b = np.zeros(hidden_dim, dtype=np.float32)
        self._policy_output = (
            np.random.randn(hidden_dim, action_dim).astype(np.float32) * 0.01
        )
        self._policy_output_b = np.zeros(action_dim, dtype=np.float32)

        logger.info(
            f"Initialized RL learner: state_dim={state_dim}, action_dim={action_dim}"
        )

    async def select_action(
        self, state: List[float], iteration: int = 0, evaluation: bool = False
    ) -> Dict[str, float]:
        """Select action based on current policy"""
        if self._state_dim == 0:
            return self._random_action()

        state_np = np.array(state, dtype=np.float32)

        if not evaluation and random.random() < self._epsilon:
            return self._random_action()

        q_values = self._forward_q(state_np)

        action = q_values.argmax()

        delta = {f"param_{i}": 0.0 for i in range(self._action_dim)}
        delta[f"param_{action}"] = 0.1 * (1.0 - iteration / 100)

        return delta

    def _forward_q(self, state: np.ndarray) -> np.ndarray:
        """Forward pass through Q network"""
        hidden = np.tanh(np.dot(state, self._q_network) + self._q_network_b)
        q_values = np.dot(hidden, self._q_network_2) + self._q_network_2_b
        return q_values

    def _forward_policy(self, state: np.ndarray) -> np.ndarray:
        """Forward pass through policy network"""
        hidden = np.tanh(np.dot(state, self._policy_network) + self._policy_b)
        action_mean = np.tanh(
            np.dot(hidden, self._policy_output) + self._policy_output_b
        )
        return action_mean

    async def store_experience(
        self,
        state: List[float],
        action: Dict[str, float],
        reward: float,
        next_state: Optional[List[float]],
        done: bool,
        trajectory_id: Optional[str] = None,
    ) -> None:
        """Store an experience in the replay buffer"""
        action_list = [action.get(f"param_{i}", 0.0) for i in range(self._action_dim)]

        self.experience_buffer.add(
            state=state,
            action=action_list,
            reward=reward,
            next_state=next_state,
            done=done,
            trajectory_id=trajectory_id,
        )

        self._current_episode_reward += reward

        if done:
            self._episode_rewards.append(self._current_episode_reward)
            self._current_episode_reward = 0.0

    async def train_step(self) -> Optional[Dict[str, float]]:
        """Perform one training step"""
        if len(self.experience_buffer._buffer) < self.config.batch_size:
            return None

        experiences, weights = self.experience_buffer.sample()

        states = np.array([exp.state for exp in experiences], dtype=np.float32)
        actions = np.array([exp.action for exp in experiences], dtype=np.float32)
        rewards = np.array([exp.reward for exp in experiences], dtype=np.float32)
        next_states = np.array(
            [exp.next_state if exp.next_state else exp.state for exp in experiences],
            dtype=np.float32,
        )
        dones = np.array([exp.done for exp in experiences], dtype=np.float32)

        if self.config.algorithm == RLAlgorithm.Q_LEARNING:
            loss = await self._train_q_learning(
                states, actions, rewards, next_states, dones
            )
        elif self.config.algorithm == RLAlgorithm.DQN:
            loss = await self._train_dqn(states, actions, rewards, next_states, dones)
        elif self.config.algorithm == RLAlgorithm.POLICY_GRADIENT:
            loss = await self._train_policy_gradient(states, actions, rewards)
        else:
            loss = await self._train_q_learning(
                states, actions, rewards, next_states, dones
            )

        self._training_step += 1

        if self._training_step % self.config.target_update_freq == 0:
            self._update_target_network()

        self._epsilon = max(
            self.config.epsilon_min, self._epsilon * self.config.epsilon_decay
        )

        return {"loss": float(loss), "epsilon": self._epsilon}

    async def _train_q_learning(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        rewards: np.ndarray,
        next_states: np.ndarray,
        dones: np.ndarray,
    ) -> float:
        """Train using Q-learning algorithm"""
        current_q = self._forward_q(states)

        next_q = self._forward_q(next_states)
        target_q = rewards + self.config.discount_factor * next_q.max(axis=1) * (
            1 - dones
        )

        action_indices = actions.argmax(axis=1)

        target_q_values = current_q.copy()
        for i, (idx, q_val) in enumerate(zip(action_indices, target_q)):
            target_q_values[i, idx] = q_val

        loss = np.mean((current_q - target_q_values) ** 2)

        self._backward_q(current_q - target_q_values)

        return loss

    async def _train_dqn(
        self,
        states: np.ndarray,
        actions: np.ndarray,
        rewards: np.ndarray,
        next_states: np.ndarray,
        dones: np.ndarray,
    ) -> float:
        """Train using Deep Q-Network algorithm"""
        return await self._train_q_learning(
            states, actions, rewards, next_states, dones
        )

    async def _train_policy_gradient(
        self, states: np.ndarray, actions: np.ndarray, rewards: np.ndarray
    ) -> float:
        """Train using Policy Gradient algorithm"""
        action_means = self._forward_policy(states)

        advantages = rewards - action_means.mean(axis=1)

        loss = -np.mean(advantages)

        return loss

    def _backward_q(self, gradients: np.ndarray) -> None:
        """Backward pass for Q network (simplified)"""
        learning_rate = self.config.learning_rate

        hidden = np.tanh(np.dot(self._q_network, gradients) + self._q_network_b)

        self._q_network -= learning_rate * np.outer(hidden, gradients)
        self._q_network_2 -= learning_rate * gradients

    def _update_target_network(self) -> None:
        """Update target network with current Q network weights"""
        self._target_network = self._q_network.copy()
        self._target_b = self._q_network_b.copy()
        self._target_network_2 = self._q_network_2.copy()
        self._target_network_2_b = self._q_network_2_b.copy()

    def _random_action(self) -> Dict[str, float]:
        """Generate random action"""
        return {
            f"param_{i}": random.uniform(-1.0, 1.0) for i in range(self._action_dim)
        }

    async def update(
        self,
        state: List[float],
        action: Dict[str, float],
        reward: float,
        next_state: Optional[List[float]],
        done: bool,
    ) -> Optional[Dict[str, float]]:
        """Update the learner with a single experience"""
        await self.store_experience(state, action, reward, next_state, done)

        if len(self.experience_buffer._buffer) >= self.config.batch_size:
            return await self.train_step()

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get learning statistics"""
        buffer_stats = self.experience_buffer.get_statistics()

        avg_reward = 0.0
        if self._episode_rewards:
            recent = self._episode_rewards[-100:]
            avg_reward = sum(recent) / len(recent)

        return {
            "algorithm": self.config.algorithm.value,
            "training_step": self._training_step,
            "epsilon": self._epsilon,
            "average_reward_100": avg_reward,
            "total_episodes": len(self._episode_rewards),
            "buffer_stats": buffer_stats,
        }

    def save_model(self, filepath: str) -> bool:
        """Save model weights"""
        try:
            data = {
                "q_network": self._q_network.tolist()
                if self._q_network is not None
                else None,
                "q_network_b": self._q_network_b.tolist()
                if self._q_network_b is not None
                else None,
                "q_network_2": self._q_network_2.tolist()
                if self._q_network_2 is not None
                else None,
                "q_network_2_b": self._q_network_2_b.tolist()
                if self._q_network_2_b is not None
                else None,
                "training_step": self._training_step,
                "epsilon": self._epsilon,
            }

            import json

            with open(filepath, "w") as f:
                json.dump(data, f)

            return True
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return False

    def load_model(self, filepath: str) -> bool:
        """Load model weights"""
        try:
            import json

            with open(filepath, "r") as f:
                data = json.load(f)

            self._q_network = (
                np.array(data["q_network"]) if data.get("q_network") else None
            )
            self._q_network_b = (
                np.array(data["q_network_b"]) if data.get("q_network_b") else None
            )
            self._q_network_2 = (
                np.array(data["q_network_2"]) if data.get("q_network_2") else None
            )
            self._q_network_2_b = (
                np.array(data["q_network_2_b"]) if data.get("q_network_2_b") else None
            )
            self._training_step = data.get("training_step", 0)
            self._epsilon = data.get("epsilon", self.config.epsilon)

            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
