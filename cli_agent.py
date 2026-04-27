#!/usr/bin/env python3
"""
Multi-Agent Guidance System - CLI End-to-End Execution
"""

import asyncio
import argparse
import math
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from multi_agent.simulation.guidance_simulator import GuidanceParameters

dotenv_path = Path(__file__).parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)

async def main(args):
    print("=" * 80)
    print("Multi-Agent Guidance System - CLI Workflow")
    print("=" * 80)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Task: {args.prompt}")
    print("=" * 80)

    # 1. Initialize components
    print("\n[Step 1] Initializing components...")
    
    from multi_agent import (
        HermesIntegration,
        HERMES_AVAILABLE,
        IntelligentTaskPlanner,
        RAGKnowledgeBase,
        ParameterExperience,
        MemoryType,
    )
    from multi_agent.simulation import GuidanceSimulator
    from multi_agent.integration.reflection_agent import ReflectionAgent
    from multi_agent.config_loader import get_config
    import multi_agent.tools as agent_tools

    rag = RAGKnowledgeBase()
    await rag.initialize()
    # # Dummy data just to ensure RAG works
    # await rag.index_documents([
    #     {"content": "比例导引律（PN）是最常用的导引方法，导航系数通常取3-5", "metadata": {"topic": "guidance_law"}},
    #     {"content": "拦截机动目标的导航系数需要增大到4-6", "metadata": {"topic": "guidance_law"}},
    #     {"content": "阻尼比0.2-0.5提供良好的系统稳定性", "metadata": {"topic": "stability"}},
    # ])
    
    parameter_experience = ParameterExperience()
    
    simulator = GuidanceSimulator(
        output_dir="./guidance_output",
        engine="octave"  # Use octave as requested
    )
    
    reflection_agent = ReflectionAgent()

    hermes = None
    hermes_available = False
    if HERMES_AVAILABLE:
        hermes = HermesIntegration()
        hermes_available = await hermes.initialize_with_tools(
            rag_kb=rag,
            parameter_experience=parameter_experience,
            simulator=simulator,
            reflection_agent=reflection_agent,
        )
        if hermes_available:
            print(f"  Hermes initialized with tools.")
    
    current_prompt = args.prompt
    max_iterations = get_config().workflow.max_iterations
    iteration = 0
    best_result = None
    study_results = []
    initial_params = None

    while iteration < max_iterations:
        iteration += 1
        print(f"\n{'='*40}")
        print(f"Iteration {iteration}/{max_iterations}")
        print(f"{'='*40}")

        # 2. Task Planning & Parameter Extraction
        print("\n[Step 2] Task Planning & Parameter Extraction...")
        extracted_params = {}
        if hermes and hermes_available:
            planner = IntelligentTaskPlanner(hermes=hermes)
            task_plan = await planner.analyze_and_plan(current_prompt)
            print(f"  Plan: {task_plan.strategy.value} strategy with {task_plan.subagent_count} subtasks")
            print(f"  Reason: {task_plan.reason}")

            # Extract parameters using LLM
            prompt_extract = f"""从以下提示词中提取制导系统的初始参数。如果未提及，请不要在 JSON 中包含该字段。

提示词：
{current_prompt}

请返回以下 JSON 格式（确保键名正确且值为数字或数字数组）：
{{
    "navigation_coefficient": 3.0,
    "damping_ratio": 0.3,
    "target_position": [18000.0, 2000.0, 5000.0],
    "target_velocity": [20000.0, 0.0, 0.0],
    "initial_position": [0.0, 7000.0, 0.0],
    "initial_velocity": [900.0, 0.0, 0.0]
}}
只返回 JSON 内容。"""
            
            llm_client = hermes.agent if hasattr(hermes, "agent") else None
            if llm_client:
                try:
                    if hasattr(llm_client, "generate"):
                        response = await llm_client.generate(prompt=prompt_extract)
                    elif hasattr(llm_client, "run_conversation"):
                        import inspect
                        if inspect.iscoroutinefunction(llm_client.run_conversation):
                            response = await llm_client.run_conversation(prompt_extract)
                        else:
                            response = llm_client.run_conversation(prompt_extract)
                        
                        if isinstance(response, dict):
                            response = response.get("final_response", "")
                    
                    # Parse JSON
                    if isinstance(response, str):
                        json_str = response.strip()
                        if json_str.startswith("```json"):
                            json_str = json_str[7:-3].strip()
                        elif json_str.startswith("```"):
                            json_str = json_str[3:-3].strip()
                        extracted_params = json.loads(json_str)
                        print(f"  Extracted Parameters: {extracted_params}")
                except Exception as e:
                    print(f"  Failed to extract parameters using LLM: {e}")
                    
        else:
            print("  Hermes not available. Skipping task planning.")
        
        # 3. Simulation & Optimization
        print("\n[Step 4] Simulation & Optimization (Octave)...")
        
        # Use baseline parameters and update with extracted ones
        initial_params = GuidanceParameters(
            navigation_coefficient=extracted_params.get("navigation_coefficient", 3.0),
            damping_ratio=extracted_params.get("damping_ratio", 0.3),
            target_position=extracted_params.get("target_position", [20000.0, 2000.0, 5000.0]),
            target_velocity=extracted_params.get("target_velocity", [0.0, 0.0, 0.0]),
            initial_position=extracted_params.get("initial_position", [0.0, 7000.0, 0.0]),
            initial_velocity=extracted_params.get("initial_velocity", [960.0, 0.0, 0.0])
        )

        study_grid = {
            "navigation_coefficient": [3.0, 4.0, 5.0],
            "damping_ratio": [0.2, 0.3, 0.4],
        }

        study_results = await simulator.parameter_study(
            param_grid=study_grid,
            duration=100.0,
            dt=0.01,
        )

        valid_results = [r for r in study_results if r["metrics"]["success"]]
        if not valid_results:
            # If external simulation fails, fallback logic usually catches it, but if it doesn't:
            print("  All simulations failed! Using best effort metrics.")
            valid_results = study_results

        best_result = min(
            valid_results,
            key=lambda r: (r["metrics"]["miss_distance"] * 1.0 + r["metrics"]["control_energy"] * 10.0),
        )

        print(f"  Best Parameters: Nav={best_result['parameters']['navigation_coefficient']}, Damping={best_result['parameters']['damping_ratio']}")
        print(f"  Best Metrics: Miss Distance={best_result['metrics']['miss_distance']:.4f}m, Control Energy={best_result['metrics']['control_energy']:.4f}J")
        
        # 3.5 Result Reflection
        print("\n[Step 3.5] Result Reflection & Discrimination...")
        reflection = await reflection_agent.reflect(current_prompt, best_result)
        
        print("  [Reflection Output]:")
        print(f"  {json.dumps(reflection, ensure_ascii=False, indent=2)}")
        
        needs_optimization = reflection.get("needs_optimization", False)
        suggestion = reflection.get("suggestion", "")
        
        print(f"  Needs Optimization: {needs_optimization}")
        print(f"  Suggestion: {suggestion}")
        
        if needs_optimization and iteration < max_iterations:
            print("  Simulation result needs optimization. Feeding back to Hermes...")
            current_prompt = f"{args.prompt}\n\n[Previous Simulation Result & Optimization Suggestion]: {suggestion}"
            continue
        elif needs_optimization and iteration >= max_iterations:
            print("  Reached max iterations. Ending loop.")
            break
        else:
            print("  Simulation result accepted! Ending loop.")
            break

    # 4. ParameterExperience Experience Writeback
    print("\n[Step 4] Writing Experience to ParameterExperience...")
    await parameter_experience.store(
        task_context={"task": "guidance_optimization", "prompt": args.prompt},
        parameters=best_result["parameters"],
        objectives={
            "miss_distance": best_result["metrics"]["miss_distance"],
            "control_energy": best_result["metrics"]["control_energy"],
        },
        fitness=1.0 / (1.0 + best_result["metrics"]["miss_distance"]),
        memory_type=MemoryType.LONG_TERM,
    )
    print("  Experience saved successfully.")

    # 5. Generate Report
    print("\n[Step 5] Generating Report...")
    report = generate_report(args.prompt, initial_params, best_result, study_results)
    
    report_path = Path("./guidance_output/report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Report saved to: {report_path}")
    print("\nWorkflow Complete!")

def _fmt(val):
    """Format number, showing nan for NaN values"""
    if isinstance(val, float) and math.isnan(val):
        return "nan"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)

def generate_report(user_input: str, params: GuidanceParameters, best: dict, study: list) -> str:
    lines = [
        "# 导引系统优化报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 任务描述",
        f"用户输入: {user_input}",
        "",
        "## 初始参数",
        f"- 导航系数: {params.navigation_coefficient}",
        f"- 阻尼比: {params.damping_ratio}",
        "",
        "## 优化结果",
        f"| 参数 | 值 |",
        f"|------|-----|",
        f"| 导航系数 | {best['parameters']['navigation_coefficient']} |",
        f"| 阻尼比 | {best['parameters']['damping_ratio']} |",
        f"| 脱靶量 | {_fmt(best['metrics']['miss_distance'])} m |",
        f"| 控制能量 | {_fmt(best['metrics']['control_energy'])} J |",
        "",
        "## 参数研究结果",
        f"| 导航系数 | 阻尼比 | 脱靶量 | 控制能量 |",
        f"|----------|--------|--------|----------|"
    ]
    for r in study:
        p = r["parameters"]
        m = r["metrics"]
        lines.append(
            f"| {p['navigation_coefficient']} | {p['damping_ratio']} | "
            f"{_fmt(m['miss_distance'])} | {_fmt(m['control_energy'])} |"
        )
    return "\n".join(lines)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Guidance CLI Agent")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt", type=str, help="User task description as string")
    group.add_argument("--file", type=str, help="Path to a text file containing the user task description")
    args = parser.parse_args()
    
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                args.prompt = f.read().strip()
        except FileNotFoundError:
            print(f"Error: Prompt file '{args.file}' not found.")
            exit(1)
            
    asyncio.run(main(args))
