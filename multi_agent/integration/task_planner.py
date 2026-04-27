#!/usr/bin/env python3
"""
Intelligent Task Planner
使用LLM决策是否拆分任务、拆分数目、执行策略
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """执行策略"""

    SINGLE = "single"  # 单Agent直接执行
    SEQUENTIAL = "sequential"  # 顺序拆分执行
    PARALLEL = "parallel"  # 并行拆分执行


@dataclass
class TaskPlan:
    """任务规划"""

    original_task: str
    strategy: ExecutionStrategy
    should_split: bool
    subagent_count: int
    subtasks: List[str]
    reason: str


class IntelligentTaskPlanner:
    """
    智能任务规划器

    使用LLM决策：
    1. 是否拆分任务
    2. 拆分成几个子任务
    3. 使用什么执行策略
    """

    def __init__(
        self,
        hermes: Any = None,
        llm_client: Any = None,
    ):
        if llm_client is None and hermes is not None:
            llm_client = hermes.agent if hasattr(hermes, "agent") else None

        self.hermes = hermes
        self.llm_client = llm_client

    async def analyze_and_plan(self, task: str) -> TaskPlan:
        """
        使用LLM分析任务并制定执行计划
        """
        if not self.llm_client and not self.hermes:
            raise RuntimeError(
                "LLM client not configured. Please provide llm_client or hermes with agent."
            )

        logger.info(f"[Planner] Analyzing task with LLM: {task[:50]}...")

        prompt = f"""分析以下任务，制定最优执行计划：

任务：{task}

请分析并返回JSON格式的计划：
{{
    "should_split": true/false,
    "strategy": "single/sequential/parallel",
    "subagent_count": 数字(1-5),
    "subtasks": ["子任务1描述", "子任务2描述", ...],
    "reason": "决策原因说明"
}}

拆分原则：
- 独立并行任务使用parallel策略
- 存在先后依赖的任务使用sequential策略
- 简单任务不需要拆分
- subagent_count建议1-5个
- subtasks数组长度应等于subagent_count

请直接返回JSON，不要其他内容："""

        import json

        try:
            if hasattr(self.hermes, "run_with_tools"):
                response = await self.hermes.run_with_tools(
                    f"System: 你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。\n\nUser: {prompt}",
                    tools=[]
                )
            elif hasattr(self.llm_client, "generate"):
                response = await self.llm_client.generate(
                    prompt=prompt,
                    system_prompt="你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。",
                )
            elif hasattr(self.llm_client, "run_conversation"):
                import inspect
                msg = f"System: 你是一个任务规划专家，擅长分析任务复杂度并制定最优执行策略。\n\nUser: {prompt}"
                if inspect.iscoroutinefunction(self.llm_client.run_conversation):
                    response = await self.llm_client.run_conversation(msg)
                else:
                    response = self.llm_client.run_conversation(msg)

                if isinstance(response, dict):
                    response = response.get("final_response", str(response))
            else:
                raise RuntimeError("No supported text generation method found on LLM client or hermes.")

            # 清理响应中可能的 markdown 代码块标记
            if response is None:
                raise RuntimeError("LLM returned None response")
            cleaned_response = response.strip()
                
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()

            data = json.loads(cleaned_response)

            return TaskPlan(
                original_task=task,
                strategy=ExecutionStrategy(data.get("strategy", "single")),
                should_split=data.get("should_split", False),
                subagent_count=data.get("subagent_count", 1),
                subtasks=data.get("subtasks", [task]),
                reason=data.get("reason", ""),
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            # Try to fix common JSON errors
            try:
                # Remove trailing commas before closing braces/brackets
                import re
                fixed = re.sub(r',\s*([}\]])', r'\1', cleaned_response)
                data = json.loads(fixed)
                logger.info("JSON fixed by removing trailing commas")
                return TaskPlan(
                    original_task=task,
                    strategy=ExecutionStrategy(data.get("strategy", "single")),
                    should_split=data.get("should_split", False),
                    subagent_count=data.get("subagent_count", 1),
                    subtasks=data.get("subtasks", [task]),
                    reason=data.get("reason", ""),
                )
            except Exception:
                pass
            raise RuntimeError(f"LLM returned invalid JSON: {locals().get('response', 'No response generated')[:200]}")
        except Exception as e:
            logger.error(f"LLM planning failed: {e}")
            raise

    async def execute(self, task: str) -> Dict[str, Any]:
        """
        智能执行任务：规划 -> 决策 -> 执行
        """
        plan = await self.analyze_and_plan(task)
        logger.info(
            f"[Planner] Plan: {plan.strategy.value}, split={plan.should_split}, count={plan.subagent_count}"
        )

        if not plan.should_split or plan.subagent_count == 1:
            return await self._execute_single(task, plan)

        elif plan.strategy == ExecutionStrategy.PARALLEL:
            return await self._execute_parallel(task, plan)

        else:
            return await self._execute_sequential(task, plan)

    async def _execute_single(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """单Agent执行"""
        if not self.hermes:
            return {
                "status": "completed",
                "strategy": "single",
                "result": f"任务已完成: {task[:50]}...",
                "subagent_count": 1,
            }

        result = await self.hermes.run_with_tools(task, tools=[])
        return {
            "status": "completed",
            "strategy": "single",
            "result": result,
            "subagent_count": 1,
            "plan_reason": plan.reason,
        }

    async def _execute_parallel(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """并行执行多个子任务"""
        from .subagent import SubagentManager, SubagentConfig

        manager = SubagentManager(self.hermes)

        results = await manager.delegate_parallel(
            tasks=plan.subtasks,
            configs=[
                SubagentConfig(name=f"parallel_{i}", max_iterations=30)
                for i in range(len(plan.subtasks))
            ],
        )

        aggregated = await manager.aggregate_results(results, strategy="all")

        return {
            "status": "completed",
            "strategy": "parallel",
            "original_task": task,
            "subtasks": plan.subtasks,
            "results": [r.result for r in results if r.status == "completed"],
            "aggregated_result": aggregated,
            "subagent_count": len(plan.subtasks),
            "plan_reason": plan.reason,
        }

    async def _execute_sequential(self, task: str, plan: TaskPlan) -> Dict[str, Any]:
        """顺序执行多个子任务"""
        from .subagent import SubagentManager, SubagentConfig

        manager = SubagentManager(self.hermes)
        all_results = []

        for i, subtask in enumerate(plan.subtasks):
            logger.info(f"[Planner] Sequential step {i + 1}/{len(plan.subtasks)}")
            result = await manager.delegate(
                task=subtask,
                config=SubagentConfig(name=f"seq_{i}", max_iterations=30),
            )
            all_results.append(result)

        return {
            "status": "completed",
            "strategy": "sequential",
            "original_task": task,
            "subtasks": plan.subtasks,
            "results": [r.result for r in all_results if r.status == "completed"],
            "subagent_count": len(plan.subtasks),
            "plan_reason": plan.reason,
        }


async def smart_execute(
    task: str,
    hermes: Any = None,
    llm_client: Any = None,
) -> Dict[str, Any]:
    """
    智能任务执行

    使用LLM自动决策：
    - 任务复杂度分析
    - 是否需要拆分
    - 执行策略选择
    - 子Agent调度
    """
    planner = IntelligentTaskPlanner(hermes=hermes, llm_client=llm_client)
    return await planner.execute(task)
