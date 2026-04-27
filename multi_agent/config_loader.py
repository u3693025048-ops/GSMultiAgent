#!/usr/bin/env python3
"""
Configuration Loader
Loads settings from config.yaml (unified configuration system)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import yaml


def get_env(key: str, default: Any = None) -> Any:
    """Get environment variable with optional default"""
    return os.environ.get(key, default)


@dataclass
class LLMConfig:
    """LLM Configuration"""
    provider: str = "openrouter"
    api_key: Optional[str] = None
    model: str = "anthropic/claude-sonnet-4.6"
    base_url: str = "https://openrouter.ai/api/v1"

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = get_env("LLM_PROVIDER", "openrouter")
        if provider == "openai":
            base_url = get_env("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = get_env("OPENAI_MODEL", "gpt-4o")
        elif provider == "anthropic":
            base_url = "https://api.anthropic.com"
            model = get_env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        elif provider == "custom":
            base_url = get_env("CUSTOM_BASE_URL", "https://api.custom.com/v1")
            model = get_env("CUSTOM_MODEL", "gpt-4o")
        else:
            base_url = "https://openrouter.ai/api/v1"
            model = get_env("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
        api_key = get_env("OPENROUTER_API_KEY") or get_env("OPENAI_API_KEY") or get_env("ANTHROPIC_API_KEY") or get_env("CUSTOM_API_KEY")
        return cls(provider=provider, api_key=api_key, model=model, base_url=base_url)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        env_config = cls.from_env()
        return cls(
            provider=data.get("provider", env_config.provider),
            api_key=data.get("api_key", env_config.api_key),
            model=data.get("model", env_config.model),
            base_url=data.get("base_url", env_config.base_url),
        )


@dataclass
class RAGConfig:
    """RAG Knowledge Base Configuration"""
    persist_dir: str = "./chroma_db"
    collection: str = "knowledge_base"
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    embedding_api_key: Optional[str] = None
    embedding_base_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> "RAGConfig":
        return cls(
            persist_dir=get_env("CHROMA_PERSIST_DIR", "./chroma_db"),
            collection=get_env("CHROMA_COLLECTION", "knowledge_base"),
            embedding_provider=get_env("EMBEDDING_PROVIDER", "local"),
            embedding_model=get_env("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            embedding_dim=int(get_env("EMBEDDING_DIM", "384")),
            embedding_api_key=get_env("EMBEDDING_API_KEY", None),
            embedding_base_url=get_env("EMBEDDING_BASE_URL", None),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGConfig":
        env_config = cls.from_env()
        return cls(
            persist_dir=data.get("persist_dir", env_config.persist_dir),
            collection=data.get("collection", env_config.collection),
            embedding_provider=data.get("embedding_provider", env_config.embedding_provider),
            embedding_model=data.get("embedding_model", env_config.embedding_model),
            embedding_dim=data.get("embedding_dim", env_config.embedding_dim),
            embedding_api_key=data.get("embedding_api_key", env_config.embedding_api_key),
            embedding_base_url=data.get("embedding_base_url", env_config.embedding_base_url),
        )


@dataclass
class ParameterExperienceConfig:
    """ParameterExperience Memory Configuration"""
    enabled: bool = True
    max_short_term: int = 100
    max_long_term: int = 1000
    similarity_threshold: float = 0.7
    decay_factor: float = 0.95

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParameterExperienceConfig":
        return cls(
            enabled=data.get("enabled", True),
            max_short_term=data.get("max_short_term", 100),
            max_long_term=data.get("max_long_term", 1000),
            similarity_threshold=data.get("similarity_threshold", 0.7),
            decay_factor=data.get("decay_factor", 0.95),
        )


@dataclass
class GAConfig:
    """Genetic Algorithm Configuration"""
    population_size: int = 50
    crossover_rate: float = 0.8
    mutation_rate: float = 0.1
    max_generations: int = 100
    tournament_size: int = 3
    elite_size: int = 2

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GAConfig":
        return cls(
            population_size=data.get("population_size", 50),
            crossover_rate=data.get("crossover_rate", 0.8),
            mutation_rate=data.get("mutation_rate", 0.1),
            max_generations=data.get("max_generations", 100),
            tournament_size=data.get("tournament_size", 3),
            elite_size=data.get("elite_size", 2),
        )


@dataclass
class OptimizerRLConfig:
    """Optimizer Reinforcement Learning Configuration"""
    algorithm: str = "q_learning"
    learning_rate: float = 0.01
    discount_factor: float = 0.95
    epsilon: float = 0.1
    epsilon_decay: float = 0.995
    epsilon_min: float = 0.01
    batch_size: int = 32
    memory_size: int = 10000

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizerRLConfig":
        return cls(
            algorithm=data.get("algorithm", "q_learning"),
            learning_rate=data.get("learning_rate", 0.01),
            discount_factor=data.get("discount_factor", 0.95),
            epsilon=data.get("epsilon", 0.1),
            epsilon_decay=data.get("epsilon_decay", 0.995),
            epsilon_min=data.get("epsilon_min", 0.01),
            batch_size=data.get("batch_size", 32),
            memory_size=data.get("memory_size", 10000),
        )


@dataclass
class OptimizerConfig:
    """Optimizer Configuration"""
    enabled: bool = True
    type: str = "ga"  # "ga" | "rl"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptimizerConfig":
        return cls(
            enabled=data.get("enabled", True),
            type=data.get("type", "ga"),
        )


@dataclass
class WorkflowConfig:
    """Workflow Configuration"""
    max_iterations: int = 3

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        return cls(
            max_iterations=data.get("max_iterations", 3),
        )


@dataclass
class AppConfig:
    """Application Configuration"""
    parameter_experience: ParameterExperienceConfig = field(default_factory=ParameterExperienceConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    ga: GAConfig = field(default_factory=GAConfig)
    rl: OptimizerRLConfig = field(default_factory=OptimizerRLConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            parameter_experience=ParameterExperienceConfig.from_dict(data.get("parameter_experience", {})),
            optimizer=OptimizerConfig.from_dict(data.get("optimizer", {})),
            ga=GAConfig.from_dict(data.get("ga", {})),
            rl=OptimizerRLConfig.from_dict(data.get("rl", {})),
            llm=LLMConfig.from_dict(data.get("llm", {})),
            rag=RAGConfig.from_dict(data.get("rag", {})),
            workflow=WorkflowConfig.from_dict(data.get("workflow", {})),
        )


def load_config(config_path: str = None) -> AppConfig:
    """Load configuration from YAML file"""
    if config_path is None:
        parent_dir_config = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
        if os.path.exists(parent_dir_config):
            config_path = parent_dir_config
        else:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

    if not os.path.exists(config_path):
        return AppConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return AppConfig.from_dict(data or {})


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get global config instance (lazy loading)"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config(config_path: str = None) -> AppConfig:
    """Reload configuration from file"""
    global _config
    _config = load_config(config_path)
    return _config
