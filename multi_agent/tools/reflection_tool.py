#!/usr/bin/env python3
"""
Reflection Agent Tool Wrapper
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ReflectionTool:
    """Tool for reflecting on simulation results to determine if optimization is needed"""

    name = "reflect_on_results"
    description = """
    Reflect on the best simulation result to determine if the parameter optimization has met the requirements.
    Use this when you have a simulation result and need to decide whether to stop or continue optimizing.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "current_prompt": {
                "type": "string",
                "description": "The current task description or prompt",
            },
            "best_result": {
                "type": "object",
                "description": "The best simulation result to evaluate, containing metrics like miss_distance and control_energy",
            }
        },
        "required": ["current_prompt", "best_result"],
    }

    def __init__(self, *args, **kwargs):
        self.reflection_agent = None
        super().__init__(*args, **kwargs)

    def set_reflection_agent(self, reflection_agent) -> None:
        """Inject the ReflectionAgent instance"""
        self.reflection_agent = reflection_agent

    async def execute(self, current_prompt: str, best_result: Dict[str, Any]) -> Dict[str, Any]:
        """Execute reflection using the ReflectionAgent"""
        if not self.reflection_agent:
            return {"status": "error", "message": "ReflectionAgent not initialized in this tool"}

        try:
            logger.info("Executing reflection tool...")
            reflection_output = await self.reflection_agent.reflect(current_prompt, best_result)
            return {
                "status": "success",
                "needs_optimization": reflection_output.get("needs_optimization", False),
                "suggestion": reflection_output.get("suggestion", ""),
                "raw_output": reflection_output
            }
        except Exception as e:
            logger.error(f"Reflection tool execution failed: {e}")
            return {"status": "error", "message": str(e)}

    # Fallback sync call if hermes executes synchronously
    def __call__(self, current_prompt: str, best_result: Dict[str, Any]) -> str:
        import asyncio
        import json
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            # Create a new thread or use nest_asyncio if needed, but for simplicity:
            # this shouldn't be reached if hermes runs async natively.
            import threading
            result = [None]
            def run():
                new_loop = asyncio.new_event_loop()
                result[0] = new_loop.run_until_complete(self.execute(current_prompt, best_result))
                new_loop.close()
            t = threading.Thread(target=run)
            t.start()
            t.join()
            return json.dumps(result[0], ensure_ascii=False)
        else:
            res = loop.run_until_complete(self.execute(current_prompt, best_result))
            return json.dumps(res, ensure_ascii=False)
