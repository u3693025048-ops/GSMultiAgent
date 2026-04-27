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
class AblationConfig:
    """Ablation study component switches.

    Each flag maps to a yaml block::

        ablation:
          rl_optimization:            { enabled: true }
          parameter_experience_reuse: { enabled: true }
          reflection_agent:           { enabled: true }
          hermes_rl_tool:             { enabled: true }

    ``hermes_rl_tool`` is a finer-grained switch than ``rl_optimization``:
    it only removes the ``matlab_rl_optimize`` tool from Hermes while
    keeping the direct Step-3 RL loop intact.
    """
    rl_optimization: bool = True
    optimization_workflow: bool = True
    parameter_experience_reuse: bool = True
    reflection_agent: bool = True
    hermes_rl_tool: bool = True
    memory_search: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AblationConfig":
        def _flag(sub: Any, default: bool = True) -> bool:
            if isinstance(sub, dict):
                return bool(sub.get("enabled", default))
            if isinstance(sub, bool):
                return sub
            return default

        return cls(
            rl_optimization=_flag(data.get("rl_optimization", {})),
            optimization_workflow=_flag(data.get("optimization_workflow", {})),
            parameter_experience_reuse=_flag(data.get("parameter_experience_reuse", {})),
            reflection_agent=_flag(data.get("reflection_agent", {})),
            hermes_rl_tool=_flag(data.get("hermes_rl_tool", {})),
            memory_search=_flag(data.get("memory_search", {})),
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
    hermes_execution: bool = True
    hermes_tool_timeout: Optional[float] = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowConfig":
        _raw = data.get("hermes_tool_timeout", None)
        _timeout = float(_raw) if _raw is not None else 0.0
        return cls(
            max_iterations=data.get("max_iterations", 3),
            hermes_execution=data.get("hermes_execution", True),
            hermes_tool_timeout=_timeout,
        )


@dataclass
class RLRewardConfig:
    """Reward function weights for MatlabRLOptimizer.
    Metrics: hit_rate (maximize), SEP (minimize), PeakNy (soft constraint),
    PM (range reward), BW (range reward).
    """
    hit_rate: float = 3.0
    # SEP (miss distance)
    sep_low_bonus: float = 2.0
    sep_low_threshold: float = 2.0
    sep_mid_weight: float = 1.0
    sep_mid_threshold: float = 5.0
    # PeakNy
    peak_ny_max: float = 20.0
    peak_ny_penalty: float = 1.0
    # PM range
    pm_bonus: float = 0.5
    pm_min: float = 30.0
    pm_max: float = 60.0
    pm_penalty: float = 0.3
    # BW range
    bw_bonus: float = 0.2
    bw_min: float = 10.0
    bw_max: float = 40.0
    bw_penalty: float = 0.1

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for MatlabRLOptimizer reward_weights."""
        import dataclasses
        return {k: float(v) for k, v in dataclasses.asdict(self).items()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RLRewardConfig":
        return cls(
            hit_rate=float(data.get("hit_rate", 3.0)),
            sep_low_bonus=float(data.get("sep_low_bonus", 2.0)),
            sep_low_threshold=float(data.get("sep_low_threshold", 2.0)),
            sep_mid_weight=float(data.get("sep_mid_weight", 1.0)),
            sep_mid_threshold=float(data.get("sep_mid_threshold", 5.0)),
            peak_ny_max=float(data.get("peak_ny_max", 20.0)),
            peak_ny_penalty=float(data.get("peak_ny_penalty", 1.0)),
            pm_bonus=float(data.get("pm_bonus", 0.5)),
            pm_min=float(data.get("pm_min", 30.0)),
            pm_max=float(data.get("pm_max", 60.0)),
            pm_penalty=float(data.get("pm_penalty", 0.3)),
            bw_bonus=float(data.get("bw_bonus", 0.2)),
            bw_min=float(data.get("bw_min", 10.0)),
            bw_max=float(data.get("bw_max", 40.0)),
            bw_penalty=float(data.get("bw_penalty", 0.1)),
        )


@dataclass
class MatlabRLOptimizerConfig:
    """PPO-based autopilot parameter optimizer"""
    max_episodes: int = 20
    nmc_per_eval: int = 10
    episodes_per_update: int = 5
    hidden_dim: int = 64
    lr_actor: float = 3e-4
    lr_critic: float = 1e-3
    gamma: float = 0.99
    clip_ratio: float = 0.2
    peak_n_max: float = 20.0
    peak_n_penalty: float = 1.0
    reward_weights: RLRewardConfig = field(default_factory=RLRewardConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MatlabRLOptimizerConfig":
        return cls(
            max_episodes=data.get("max_episodes", 20),
            nmc_per_eval=data.get("nmc_per_eval", 10),
            episodes_per_update=data.get("episodes_per_update", 5),
            hidden_dim=data.get("hidden_dim", 64),
            lr_actor=float(data.get("lr_actor", 3e-4)),
            lr_critic=float(data.get("lr_critic", 1e-3)),
            gamma=float(data.get("gamma", 0.99)),
            clip_ratio=float(data.get("clip_ratio", 0.2)),
            peak_n_max=float(data.get("peak_n_max", 20.0)),
            peak_n_penalty=float(data.get("peak_n_penalty", 1.0)),
            reward_weights=RLRewardConfig.from_dict(data.get("reward_weights", {})),
        )


@dataclass
class ModelOutputConfig:
    """Model file output paths"""
    generated_dir: str = "./guidance_output/models"
    success_dir: str = "./parameter_experience_base/models"
    matlab_scripts_dir: str = "./matlab_scripts"
    experience_base_dir: str = "./parameter_experience_base"
    sysml_output_dir: str = "./guidance_output/sysml"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelOutputConfig":
        return cls(
            generated_dir=data.get("generated_dir", "./guidance_output/models"),
            success_dir=data.get("success_dir", "./parameter_experience_base/models"),
            matlab_scripts_dir=data.get("matlab_scripts_dir", "./matlab_scripts"),
            experience_base_dir=data.get("experience_base_dir", "./parameter_experience_base"),
            sysml_output_dir=data.get("sysml_output_dir", "./guidance_output/sysml"),
        )


@dataclass
class SimulationConfig:
    """Simulation engine configuration.

    The ``engine`` field accepts:

    * ``"auto"``           — auto-detect (matlab_engine > matlab > octave > python)
    * ``"matlab_engine"``  — in-process MATLAB Engine API for Python
    * ``"matlab"``         — MATLAB CLI subprocess (``matlab -batch ...``)
    * ``"octave"``         — GNU Octave subprocess
    * ``"python"``         — pure-Python fallback simulator

    Env vars ``SIMULATION_ENGINE`` / ``MATLAB_PATH`` / ``OCTAVE_PATH``
    override these values at runtime — see
    :func:`multi_agent.simulation.engine_resolver.resolve_engine_config`.
    """
    engine: str = "auto"
    octave_path: str = "octave"
    matlab_path: str = "matlab"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimulationConfig":
        return cls(
            engine=data.get("engine", "auto"),
            octave_path=data.get("octave_path", "octave"),
            matlab_path=data.get("matlab_path", "matlab"),
        )


@dataclass
class AppConfig:
    """Application Configuration"""
    ablation: AblationConfig = field(default_factory=AblationConfig)
    parameter_experience: ParameterExperienceConfig = field(default_factory=ParameterExperienceConfig)
    optimizer: OptimizerConfig = field(default_factory=OptimizerConfig)
    ga: GAConfig = field(default_factory=GAConfig)
    rl: OptimizerRLConfig = field(default_factory=OptimizerRLConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    matlab_rl_optimizer: MatlabRLOptimizerConfig = field(default_factory=MatlabRLOptimizerConfig)
    model_output: ModelOutputConfig = field(default_factory=ModelOutputConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        return cls(
            ablation=AblationConfig.from_dict(data.get("ablation", {})),
            parameter_experience=ParameterExperienceConfig.from_dict(data.get("parameter_experience", {})),
            optimizer=OptimizerConfig.from_dict(data.get("optimizer", {})),
            ga=GAConfig.from_dict(data.get("ga", {})),
            rl=OptimizerRLConfig.from_dict(data.get("rl", {})),
            llm=LLMConfig.from_dict(data.get("llm", {})),
            rag=RAGConfig.from_dict(data.get("rag", {})),
            workflow=WorkflowConfig.from_dict(data.get("workflow", {})),
            matlab_rl_optimizer=MatlabRLOptimizerConfig.from_dict(data.get("matlab_rl_optimizer", {})),
            model_output=ModelOutputConfig.from_dict(data.get("model_output", {})),
            simulation=SimulationConfig.from_dict(data.get("simulation", {})),
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
