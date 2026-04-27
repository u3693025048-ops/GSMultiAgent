#!/usr/bin/env python3
"""
Hermes Agent Integration Layer
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import warnings
warnings.filterwarnings("ignore", message="Could not import tool module")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.propagate = False


HERMES_AVAILABLE = False
HermesIntegration = None


def load_env():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


load_env()

try:
    from run_agent import AIAgent

    HERMES_AVAILABLE = True

    class HermesIntegration:
        """Hermes Agent wrapper"""

        def __init__(
            self,
            model: str = None,
            provider: str = None,
            api_key: str = None,
        ):
            from ..config_loader import get_config

            cfg = get_config().llm

            self.model = model or cfg.model
            self.provider = provider or cfg.provider
            self.api_key = api_key or cfg.api_key
            self.base_url = cfg.base_url
            self.agent: Optional[Any] = None
            self._initialized = False

        async def initialize(self) -> bool:
            if not HERMES_AVAILABLE:
                return False
            try:
                self.agent = AIAgent(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    provider=self.provider,
                    model=self.model,
                    max_iterations=90,
                )
                self._initialized = True
                logger.info(f"Hermes initialized: {self.model}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Hermes: {e}")
                return False

        async def run_with_tools(self, user_message: str, tools: List[Any] = None) -> str:
            if tools is None:
                tools = []
            if not self._initialized:
                await self.initialize()
            if not self.agent:
                return "Hermes Agent not available"
            try:
                # Only update tools if non-empty list is provided
                if tools:
                    # Format tools to JSON schema format expected by the LLM client
                    formatted_tools = []
                    for tool in tools:
                        if hasattr(tool, "input_schema") and hasattr(tool, "name") and hasattr(tool, "description"):
                            formatted_tools.append({
                                "type": "function",
                                "function": {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "parameters": tool.input_schema
                                }
                            })
                        else:
                            formatted_tools.append(tool) # Fallback to original if not a standard tool

                    self.agent.tools = formatted_tools
                # else: keep existing self.agent.tools

                import inspect
                if inspect.iscoroutinefunction(self.agent.run_conversation):
                    response = await self.agent.run_conversation(user_message)
                else:
                    response = self.agent.run_conversation(user_message)
                
                if isinstance(response, dict):
                    return response.get("final_response", str(response))
                return response
            except Exception as e:
                logger.error(f"Conversation failed: {e}")
                return None

        async def generate_text(self, prompt: str) -> str:
            """Simple text generation using the agent"""
            return await self.run_with_tools(prompt, tools=[])

        def get_all_tools(self) -> List[Any]:
            """Get all available tools from the tools directory"""
            from ..tools import (
                RAGRetrievalTool,
                RAGIndexTool,
                ParameterExperienceSearchTool,
                ParameterExperienceStoreTool,
                ParameterExperienceBestTool,
                ParameterExperienceStatsTool,
                MemorySearchTool,
                MemoryStoreTool,
                MemoryStatsTool,
                OptimizationTool,
                GenerateSysMLTool,
                GenerateMATLABTool,
                RunSimulationTool,
                ParameterStudyTool,
                OptimizeParametersTool,
                ReflectionTool,
            )
            from ..tools.optimization_tool import SimulationTool, OptimizationWithSimulationTool

            tools = [
                RAGRetrievalTool(),
                RAGIndexTool(),
                ParameterExperienceSearchTool(),
                ParameterExperienceStoreTool(),
                ParameterExperienceBestTool(),
                ParameterExperienceStatsTool(),
                MemorySearchTool(),
                MemoryStoreTool(),
                MemoryStatsTool(),
                OptimizationTool(),
                SimulationTool(),
                OptimizationWithSimulationTool(),
                GenerateSysMLTool(),
                GenerateMATLABTool(),
                RunSimulationTool(),
                ParameterStudyTool(),
                OptimizeParametersTool(),
                ReflectionTool(),
            ]
            return tools

        def format_tools_for_agent(self, tools: List[Any]) -> List[Dict[str, Any]]:
            """Format tools to JSON schema format expected by the LLM client"""
            formatted_tools = []
            for tool in tools:
                if hasattr(tool, "input_schema") and hasattr(tool, "name") and hasattr(tool, "description"):
                    formatted_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema
                        }
                    })
                else:
                    formatted_tools.append(tool)
            return formatted_tools

        async def initialize_with_tools(
            self,
            rag_kb=None,
            parameter_experience=None,
            simulator=None,
            optimizer=None,
            orchestrator=None,
            reflection_agent=None,
        ) -> bool:
            """Initialize Hermes agent with all tools registered"""
            if not HERMES_AVAILABLE:
                return False
            try:
                self.agent = AIAgent(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    provider=self.provider,
                    model=self.model,
                    max_iterations=90,
                )
                tools = self.get_all_tools()

                # Inject dependencies into tools
                for tool in tools:
                    if rag_kb and hasattr(tool, "set_rag_kb"):
                        tool.set_rag_kb(rag_kb)
                    if parameter_experience and hasattr(tool, "set_parameter_experience"):
                        tool.set_parameter_experience(parameter_experience)
                    if simulator and hasattr(tool, "set_simulator"):
                        tool.set_simulator(simulator)
                    if optimizer and hasattr(tool, "set_optimizer"):
                        tool.set_optimizer(optimizer)
                    if orchestrator and hasattr(tool, "set_orchestrator"):
                        tool.set_orchestrator(orchestrator)
                    if reflection_agent and hasattr(tool, "set_reflection_agent"):
                        tool.set_reflection_agent(reflection_agent)

                self.agent.tools = self.format_tools_for_agent(tools)
                self._initialized = True
                logger.info(f"Hermes initialized with {len(tools)} tools")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Hermes with tools: {e}")
                return False

except ImportError as e:
    logger.warning(f"Hermes Agent not available: {e}")
    HermesIntegration = None
