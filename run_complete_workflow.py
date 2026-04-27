#!/usr/bin/env python3
"""
Multi-Agent Guidance System - Complete Workflow Demo
从输入到输出的完整多智能体协同演示
"""

import asyncio
import os
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from multi_agent.simulation.guidance_simulator import GuidanceParameters

dotenv_path = Path(__file__).parent / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path)


async def main():
    print("=" * 80)
    print("Multi-Agent Guidance System - Complete Workflow")
    print("=" * 80)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # =====================================================================
    # 阶段1: 初始化所有组件
    # =====================================================================
    print("\n[阶段1] 初始化组件...")

    from multi_agent import (
        HermesIntegration,
        HERMES_AVAILABLE,
        IntelligentTaskPlanner,
        RAGKnowledgeBase,
        ParameterExperience,
        MemoryType,
        ReinforcementLearner,
        RLModuleConfig as RLConfig,
        RLAlgorithm,
    )
    from multi_agent.simulation import GuidanceSimulator, GuidanceParameters
    from multi_agent.tools import (
        RAGRetrievalTool,
        RAGIndexTool,
        ParameterExperienceSearchTool,
        ParameterExperienceStoreTool,
        GenerateSysMLTool,
        GenerateMATLABTool,
        RunSimulationTool,
        ParameterStudyTool,
        MemorySearchTool,
        MemoryStoreTool,
    )

    # 初始化 RAG 知识库
    print("  [1.1] 初始化 RAG 知识库...")
    rag = RAGKnowledgeBase()
    await rag.initialize()

    # 索引制导系统相关知识
    await rag.index_documents(
        [
            {
                "content": "比例导引律（PN）是最常用的导引方法，导航系数通常取3-5",
                "metadata": {"topic": "guidance_law"},
            },
            {
                "content": "拦截机动目标的导航系数需要增大到4-6",
                "metadata": {"topic": "guidance_law"},
            },
            {"content": "阻尼比0.2-0.5提供良好的系统稳定性", "metadata": {"topic": "stability"}},
            {"content": "脱靶量小于10m为合格，小于1m为优秀", "metadata": {"topic": "performance"}},
            {"content": "控制能量消耗与导引律效率相关", "metadata": {"topic": "efficiency"}},
        ]
    )
    print(f"  [1.1] RAG 已索引 5 篇文档")

    # 初始化 ParameterExperience 记忆
    print("  [1.2] 初始化 ParameterExperience 记忆...")
    parameter_experience = ParameterExperience()
    await parameter_experience.store(
        task_context={"task": "guidance_optimization", "scenario": "stationary_target"},
        parameters={"nav_coeff": 3.0, "damping": 0.3},
        objectives={"miss_distance": 0.5, "control_energy": 0.15},
        fitness=0.85,
        memory_type=MemoryType.LONG_TERM,
    )
    print(f"  [1.2] ParameterExperience 初始化完成")

    # 初始化仿真器
    print("  [1.3] 初始化仿真器...")
    simulator = GuidanceSimulator(output_dir="./guidance_output")
    print(f"  [1.3] 仿真器就绪")

    # 初始化 Hermes Agent
    hermes = None
    hermes_available = False
    if HERMES_AVAILABLE:
        print("  [1.4] 初始化 Hermes Agent...")
        hermes = HermesIntegration()
        hermes_available = await hermes.initialize()
        if hermes_available:
            print(f"       Hermes: {hermes.model}")
        else:
            print("       Hermes 初始化失败，将使用模拟模式")
    else:
        print("  [1.4] Hermes 未安装，使用模拟模式")

    # =====================================================================
    # 阶段2: 用户输入处理
    # =====================================================================
    print("\n[阶段2] 用户输入处理...")

    user_input = "优化导引系统参数，目标是最小化脱靶量，同时控制能量消耗不超过0.2"
    print(f"  用户输入: {user_input}")

    # =====================================================================
    # 阶段3: RAG 知识检索
    # =====================================================================
    print("\n[阶段3] RAG 知识检索...")

    rag_results = await rag.retrieve("导引律 导航系数 优化", top_k=3)
    print(f"  检索到 {len(rag_results)} 篇相关文档:")
    for i, r in enumerate(rag_results, 1):
        print(f"    [{i}] Score: {r['score']:.3f}")
        print(f"        {r['content'][:50]}...")

    # =====================================================================
    # 阶段4: ParameterExperience 经验检索
    # =====================================================================
    print("\n[阶段4] ParameterExperience 经验检索...")

    similar_exp = await parameter_experience.retrieve_similar(query={"task": "guidance_optimization"}, top_k=3)
    print(f"  找到 {len(similar_exp)} 条相似经验")

    # =====================================================================
    # 阶段5: 任务规划（LLM决策）
    # =====================================================================
    print("\n[阶段5] 任务规划...")

    if hermes and hermes_available:
        planner = IntelligentTaskPlanner(hermes=hermes)
        task_plan = await planner.analyze_and_plan(user_input)
        print(f"  规划决策:")
        print(f"    - 是否拆分: {task_plan.should_split}")
        print(f"    - 执行策略: {task_plan.strategy.value}")
        print(f"    - 子任务数: {task_plan.subagent_count}")
        print(f"    - 决策原因: {task_plan.reason}")
    else:
        task_plan = None
        print("  [模拟] 任务规划: 简单任务，单Agent执行")

    # =====================================================================
    # 阶段6: 仿真执行
    # =====================================================================
    print("\n[阶段6] 仿真执行...")

    # 设置初始参数 (基于 测试例子.txt 工况31：强侧向机动目标)
    initial_params = GuidanceParameters(
        navigation_coefficient=3.0,
        damping_ratio=0.3,
        target_position=[20000.0, 2000.0, 5000.0],
        target_velocity=[0.0, 0.0, 0.0],
        target_velocity_expr=["0.0", "100*sin(0.2*t)", "0.0"], # 测试例子.txt: T_Vy=100sin(0.2t)
        initial_position=[0.0, 7000.0, 0.0],
        initial_velocity=[960.0, 0.0, 0.0],
        initial_angles=[0.0, 0.0, 0.0],
        gama_max=45.0,
        scenario_id=31
    )

    # 单次仿真
    print("  [6.1] 单次仿真...")
    single_result = await simulator.generate_and_simulate(
        params=initial_params,
        duration=100.0,
        dt=0.01,
        generate_sysml=True,
        generate_matlab=True,
    )

    sim_metrics = single_result["simulation_result"]
    print(f"       脱靶量: {sim_metrics['miss_distance']:.6f} m")
    print(f"       控制能量: {sim_metrics['control_energy']:.6f} J")
    print(f"       成功: {sim_metrics['success']}")

    # 生成文件
    sysml_files = single_result["generated_files"].get("sysml", {})
    matlab_files = single_result["generated_files"].get("matlab", {})
    print(f"       生成文件:")
    print(f"         SysML: {list(sysml_files.keys())}")
    print(f"         MATLAB: {list(matlab_files.keys())}")

    # 参数研究
    print("  [6.2] 参数研究 (9组参数组合)...")
    study_grid = {
        "navigation_coefficient": [3.0, 4.0, 5.0],
        "damping_ratio": [0.2, 0.3, 0.4],
    }

    study_results = await simulator.parameter_study(
        param_grid=study_grid,
        duration=100.0,
        dt=0.01,
    )

    # 找到最优参数
    valid_results = [r for r in study_results if r["metrics"]["success"]]
    best_result = min(
        valid_results,
        key=lambda r: (
            r["metrics"]["miss_distance"] * 1.0  # 脱靶量权重
            + r["metrics"]["control_energy"] * 10.0  # 控制能量权重
        ),
    )

    print(f"       完成 {len(study_results)} 组仿真")
    print(f"       最优参数:")
    print(f"         导航系数: {best_result['parameters']['navigation_coefficient']}")
    print(f"         阻尼比: {best_result['parameters']['damping_ratio']}")
    print(f"         脱靶量: {best_result['metrics']['miss_distance']:.6f} m")
    print(f"         控制能量: {best_result['metrics']['control_energy']:.6f} J")

    # RL优化
    print("  [6.3] RL强化学习优化...")
    rl_result = await simulator.rl_optimize(
        initial_params=GuidanceParameters(
            navigation_coefficient=3.0,
            damping_ratio=0.3,
            target_position=[20000.0, 2000.0, 5000.0],
            target_velocity=[250.0, 0.0, 0.0],
            target_velocity_expr=["250.0", "0.0", "0.0"],
            initial_position=[0.0, 7000.0, 0.0],
            initial_velocity=[960.0, 0.0, 0.0],
            initial_angles=[0.0, 0.0, 0.0],
            gama_max=45.0,
            scenario_id=2
        ),
        param_bounds={
            "navigation_coefficient": (2.0, 6.0),
            "damping_ratio": (0.1, 0.8),
            "control_gain": (0.5, 2.0),
        },
        episodes=20,
        max_steps_per_episode=10,
        duration=100.0,
        dt=0.01,
        energy_constraint=0.2,
        target_miss_distance=1.0,
    )

    print(f"       RL优化完成!")
    print(f"       最优参数 (RL):")
    print(f"         导航系数: {rl_result['best_parameters']['navigation_coefficient']:.4f}")
    print(f"         阻尼比: {rl_result['best_parameters']['damping_ratio']:.4f}")
    print(f"         脱靶量: {rl_result['best_metrics']['miss_distance']:.6f} m")
    print(f"         控制能量: {rl_result['best_metrics']['control_energy']:.6f} J")
    print(f"       训练统计: {rl_result['learner_stats']}")

    # =====================================================================
    # 阶段7: 结果存储到 ParameterExperience
    # =====================================================================
    print("\n[阶段7] 存储到 ParameterExperience...")

    await parameter_experience.store(
        task_context={"task": "guidance_optimization", "scenario": "stationary_target"},
        parameters=best_result["parameters"],
        objectives={
            "miss_distance": best_result["metrics"]["miss_distance"],
            "control_energy": best_result["metrics"]["control_energy"],
        },
        fitness=1.0 / (1.0 + best_result["metrics"]["miss_distance"]),
        memory_type=MemoryType.LONG_TERM,
    )

    parameter_experience_stats = await parameter_experience.get_statistics()
    print(
        f"       ParameterExperience 统计: short={parameter_experience_stats['short_term_count']}, long={parameter_experience_stats['long_term_count']}"
    )

    # =====================================================================
    # 阶段8: 生成报告
    # =====================================================================
    print("\n[阶段8] 生成报告...")

    report = generate_report(user_input, initial_params, best_result, study_results)
    print(report)

    # 保存报告
    report_path = Path("./guidance_output/report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已保存: {report_path}")

    # =====================================================================
    # 完成
    # =====================================================================
    print("\n" + "=" * 80)
    print("Workflow 完成!")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


def generate_report(user_input: str, params: GuidanceParameters, best: dict, study: list) -> str:
    """生成优化报告"""

    lines = [
        "# 导引系统优化报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 任务描述",
        "",
        f"用户输入: {user_input}",
        "",
        "## 初始参数",
        "",
        f"- 导航系数: {params.navigation_coefficient}",
        f"- 阻尼比: {params.damping_ratio}",
        f"- 目标位置: {params.target_position}",
        "",
        "## 优化结果",
        "",
        f"| 参数 | 值 |",
        f"|------|-----|",
        f"| 导航系数 | {best['parameters']['navigation_coefficient']} |",
        f"| 阻尼比 | {best['parameters']['damping_ratio']} |",
        f"| 脱靶量 | {best['metrics']['miss_distance']:.6f} m |",
        f"| 控制能量 | {best['metrics']['control_energy']:.6f} J |",
        "",
        "## 参数研究结果",
        "",
        f"| 导航系数 | 阻尼比 | 脱靶量 | 控制能量 |",
        f"|----------|--------|--------|----------|",
    ]

    for r in study:
        p = r["parameters"]
        m = r["metrics"]
        lines.append(
            f"| {p['navigation_coefficient']} | {p['damping_ratio']} | "
            f"{m['miss_distance']:.4f} | {m['control_energy']:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"最优参数组合: 导航系数={best['parameters']['navigation_coefficient']}, "
            f"阻尼比={best['parameters']['damping_ratio']}",
            "",
            f"达到性能: 脱靶量={best['metrics']['miss_distance']:.4f}m, "
            f"控制能量={best['metrics']['control_energy']:.4f}J",
        ]
    )

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(main())
