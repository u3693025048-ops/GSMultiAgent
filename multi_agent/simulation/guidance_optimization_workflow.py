#!/usr/bin/env python3
"""
Guidance Optimization Workflow
整合优化器 + 仿真 + SysML/MATLAB 代码生成的完整工作流
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .guidance_simulator import (
    GuidanceSimulator,
    GuidanceParameters,
    SysMLModelGenerator,
    MATLABScriptGenerator,
    SimulationResult,
)
from ..optimizers import (
    BaseOptimizer,
    OptimizationResult,
    OptimizerFactory,
    GeneticOptimizer,
    RLOptimizer,
    OptimizerRegistry,
)
from ..config_loader import (
    load_config,
    AppConfig,
    GAConfig,
    OptimizerConfig,
    OptimizerRLConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class OptimizationObjectives:
    """优化目标定义"""
    miss_distance: bool = True
    miss_distance_weight: float = 1.0
    miss_distance_target: float = 0.0
    control_energy: bool = False
    control_energy_weight: float = 0.5
    control_energy_target: float = 0.0
    overshoot: bool = False
    overshoot_weight: float = 0.3
    overshoot_target: float = 0.0


class GuidanceOptimizationWorkflow:
    """
    制导系统优化工作流

    1. 使用配置的优化器 (GA/RL) 进行参数优化
    2. 迭代运行仿真评估目标函数
    3. 生成优化的 SysML 模型和 MATLAB 脚本
    """

    def __init__(
        self,
        output_dir: str = "./guidance_optimization_output",
        config: Optional[AppConfig] = None,
    ):
        self.output_dir = output_dir
        self.config = config or load_config()

        # Create output directories
        self.sysml_dir = os.path.join(output_dir, "sysml")
        self.matlab_dir = os.path.join(output_dir, "matlab")
        self.results_dir = os.path.join(output_dir, "results")

        for d in [self.sysml_dir, self.matlab_dir, self.results_dir]:
            os.makedirs(d, exist_ok=True)

        # Get simulation config
        sim_config = getattr(self.config, 'simulation', None) or {}
        engine = sim_config.get('engine', 'python') if isinstance(sim_config, dict) else 'python'
        octave_path = sim_config.get('octave_path', 'octave') if isinstance(sim_config, dict) else 'octave'
        matlab_path = sim_config.get('matlab_path', 'matlab') if isinstance(sim_config, dict) else 'matlab'

        # Initialize components
        self.simulator = GuidanceSimulator(
            output_dir=output_dir,
            engine=engine,
            octave_path=octave_path,
            matlab_path=matlab_path,
        )
        self.sysml_generator = SysMLModelGenerator(output_dir=self.sysml_dir)
        self.matlab_generator = MATLABScriptGenerator(output_dir=self.matlab_dir)

        # Create optimizer from config
        self.optimizer = OptimizerFactory.create(
            self.config.optimizer,
            self.config.ga,
            self.config.rl,
        )

        logger.info(f"Initialized workflow with optimizer: {self.optimizer.name}, engine: {engine}")

    async def run_optimization(
        self,
        initial_params: Optional[GuidanceParameters] = None,
        objectives: Optional[OptimizationObjectives] = None,
        param_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
        max_iterations: int = 50,
    ) -> Dict[str, Any]:
        """
        运行完整优化流程

        Args:
            initial_params: 初始参数 (默认使用配置)
            objectives: 优化目标
            param_bounds: 参数边界
            max_iterations: 最大迭代次数

        Returns:
            优化结果包含最优参数、仿真指标、生成的文件
        """
        # Default parameters
        if initial_params is None:
            initial_params = GuidanceParameters(
                navigation_coefficient=3.0,
                damping_ratio=0.3,
                control_gain=1.0,
            )

        # Default objectives
        if objectives is None:
            objectives = OptimizationObjectives(
                miss_distance=True,
                miss_distance_weight=1.0,
                control_energy=True,
                control_energy_weight=0.5,
            )

        # Default bounds
        if param_bounds is None:
            param_bounds = {
                "navigation_coefficient": (0.3, 0.7),
                "damping_ratio": (0.2, 0.5),
                "control_gain": (0.5, 1.5),
            }

        # Build objective dict for optimizer
        obj_dict = self._build_objective_dict(objectives)

        # Build initial params dict
        initial_dict = {
            "navigation_coefficient": initial_params.navigation_coefficient,
            "damping_ratio": initial_params.damping_ratio,
        }

        # Build constraints
        constraints = {}
        for name, (min_val, max_val) in param_bounds.items():
            constraints[name] = {"min": min_val, "max": max_val}

        logger.info(f"Starting optimization with {self.optimizer.name}")
        logger.info(f"Initial params: {initial_dict}")
        logger.info(f"Objectives: {obj_dict}")

        # Run optimization
        opt_result = await self.optimizer.optimize(
            objectives=obj_dict,
            constraints=constraints,
            initial_params=initial_dict,
            max_iterations=max_iterations,
        )

        # Get best parameters
        best_params = opt_result.best_parameters

        # Create optimized GuidanceParameters
        optimized_params = GuidanceParameters(
            navigation_coefficient=best_params.get("navigation_coefficient", 3.0),
            damping_ratio=best_params.get("damping_ratio", 0.3),
            control_gain=initial_params.control_gain,
            target_position=initial_params.target_position.copy(),
            initial_position=initial_params.initial_position.copy(),
            initial_velocity=initial_params.initial_velocity.copy(),
        )

        # Run final simulation with best parameters
        final_result = await self.simulator.executor.run_simulation(
            optimized_params,
            duration=100.0,
            dt=0.01,
        )

        # Generate output files
        generated_files = {}

        # Generate SysML
        sysml_files = self.sysml_generator.save_model(optimized_params, "OptimizedGuidance")
        generated_files["sysml"] = sysml_files

        # Generate MATLAB
        matlab_files = self.matlab_generator.save_scripts(
            optimized_params,
            duration=100.0,
            dt=0.01,
            param_ranges=param_bounds,
            objectives=["miss_distance", "control_energy"] if objectives.control_energy else ["miss_distance"],
        )
        generated_files["matlab"] = matlab_files

        # Compile results
        result = {
            "timestamp": datetime.now().isoformat(),
            "optimizer": self.optimizer.name,
            "optimization_result": {
                "status": opt_result.status,
                "message": opt_result.message,
                "iterations": opt_result.iterations,
                "evaluations": opt_result.evaluations,
                "best_fitness": opt_result.best_fitness,
                "history": opt_result.history,
            },
            "best_parameters": best_params,
            "simulation_metrics": {
                "miss_distance": final_result.miss_distance,
                "control_energy": final_result.control_energy,
                "max_overshoot": final_result.max_overshoot,
                "settling_time": final_result.settling_time,
                "execution_time": final_result.execution_time,
            },
            "generated_files": generated_files,
        }

        # Save results
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(
            self.results_dir,
            f"optimization_result_{timestamp_str}.json"
        )
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # Generate Markdown report
        md_report = self._generate_markdown_report(result, initial_params, objectives)
        report_file = os.path.join(
            self.results_dir,
            f"optimization_report_{timestamp_str}.md"
        )
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(md_report)

        result["report_file"] = report_file
        
        logger.info(f"Optimization complete. Results saved to: {results_file}")
        logger.info(f"Markdown report saved to: {report_file}")
        logger.info(f"Best parameters: {best_params}")
        logger.info(f"Best metrics: miss_distance={final_result.miss_distance:.6f}, "
                    f"control_energy={final_result.control_energy:.6f}")

        return result

    def _generate_markdown_report(self, result: Dict[str, Any], initial_params: GuidanceParameters, objectives: OptimizationObjectives) -> str:
        """生成 Markdown 格式的优化报告"""
        timestamp = result["timestamp"]
        optimizer_name = result["optimizer"]
        best_params = result["best_parameters"]
        metrics = result["simulation_metrics"]
        opt_res = result["optimization_result"]
        gen_files = result["generated_files"]

        lines = [
            "# 制导模型优化迭代报告",
            "",
            f"**生成时间**: {timestamp}",
            f"**优化算法**: {optimizer_name.upper()}",
            "",
            "## 1. 优化目标与约束",
            "",
            "- **脱靶量 (Miss Distance)**: " + ("优化 (最小化)" if objectives.miss_distance else "未优化"),
            "- **控制能量 (Control Energy)**: " + ("优化 (最小化)" if objectives.control_energy else "未优化"),
            "- **过载/超调 (Overshoot)**: " + ("优化 (最小化)" if objectives.overshoot else "未优化"),
            "",
            "## 2. 初始参数",
            "",
            f"- **导航系数**: {initial_params.navigation_coefficient}",
            f"- **阻尼比**: {initial_params.damping_ratio}",
            f"- **控制增益**: {initial_params.control_gain}",
            "",
            "## 3. 优化迭代结果",
            "",
            f"- **优化状态**: {opt_res['status']} ({opt_res.get('message', '')})",
            f"- **迭代次数**: {opt_res['iterations']}",
            f"- **评估次数**: {opt_res['evaluations']}",
            f"- **最优适应度**: {opt_res.get('best_fitness', 0.0):.6f}",
            "",
            "### 最优参数配置",
            "",
            "| 参数名 | 最优值 |",
            "|--------|--------|",
        ]
        
        for k, v in best_params.items():
            lines.append(f"| {k} | {v:.6f} |")
            
        lines.extend([
            "",
            "### 仿真性能指标",
            "",
            "| 指标 | 值 |",
            "|------|----|",
            f"| 脱靶量 (Miss Distance) | {metrics['miss_distance']:.6f} m |",
            f"| 控制能量 (Control Energy) | {metrics['control_energy']:.6f} J |",
            f"| 最大超调量 (Max Overshoot) | {metrics['max_overshoot']:.6f} |",
            f"| 调节时间 (Settling Time) | {metrics['settling_time']:.6f} s |",
            "",
            "## 4. 生成的产物",
            "",
            "### SysML 模型文件",
        ])
        
        for file_name, file_path in gen_files.get("sysml", {}).items():
            lines.append(f"- `{file_name}`: `{file_path}`")
            
        lines.extend([
            "",
            "### MATLAB 脚本文件",
        ])
        
        for file_name, file_path in gen_files.get("matlab", {}).items():
            lines.append(f"- `{file_name}`: `{file_path}`")
            
        lines.extend([
            "",
            "## 5. 结论",
            "",
            f"经过 **{opt_res['iterations']}** 次迭代，模型参数已完成优化。脱靶量达到 **{metrics['miss_distance']:.6f} m**，控制能量消耗为 **{metrics['control_energy']:.6f} J**。",
            "",
            "优化后的模型与相关仿真代码已成功生成，可用于进一步的系统验证与硬件在环测试。"
        ])

        return "\n".join(lines)

    def _build_objective_dict(self, objectives: OptimizationObjectives) -> Dict[str, Any]:
        """构建优化器所需的目标字典"""
        obj_dict = {}

        if objectives.miss_distance:
            obj_dict["miss_distance"] = {
                "type": "minimize",
                "weight": objectives.miss_distance_weight,
                "target": objectives.miss_distance_target,
            }

        if objectives.control_energy:
            obj_dict["control_energy"] = {
                "type": "minimize",
                "weight": objectives.control_energy_weight,
                "target": objectives.control_energy_target,
            }

        if objectives.overshoot:
            obj_dict["overshoot"] = {
                "type": "minimize",
                "weight": objectives.overshoot_weight,
                "target": objectives.overshoot_target,
            }

        return obj_dict

    async def run_comparison(
        self,
        initial_params: Optional[GuidanceParameters] = None,
        param_bounds: Optional[Dict[str, Tuple[float, float]]] = None,
        iterations: int = 30,
    ) -> Dict[str, Any]:
        """
        对比 GA 和 RL 优化器效果

        Returns:
            包含两种优化器结果的对比报告
        """
        if initial_params is None:
            initial_params = GuidanceParameters()

        if param_bounds is None:
            param_bounds = {
                "navigation_coefficient": (0.3, 0.7),
                "damping_ratio": (0.2, 0.5),
            }

        objectives = OptimizationObjectives(
            miss_distance=True,
            miss_distance_weight=1.0,
        )

        results = {}

        # Test GA
        logger.info("Running GA optimization...")
        ga_optimizer = GeneticOptimizer(
            population_size=20,
            max_generations=iterations,
        )
        ga_result = await self._optimize_with_optimizer(
            ga_optimizer, initial_params, objectives, param_bounds, iterations
        )
        results["ga"] = ga_result

        # Test RL
        logger.info("Running RL optimization...")
        rl_optimizer = RLOptimizer(
            epsilon=0.2,
            epsilon_decay=0.98,
        )
        rl_result = await self._optimize_with_optimizer(
            rl_optimizer, initial_params, objectives, param_bounds, iterations
        )
        results["rl"] = rl_result

        # Generate comparison report
        comparison = {
            "timestamp": datetime.now().isoformat(),
            "ga_best_fitness": results["ga"]["optimization_result"]["best_fitness"],
            "ga_best_params": results["ga"]["best_parameters"],
            "ga_miss_distance": results["ga"]["simulation_metrics"]["miss_distance"],
            "rl_best_fitness": results["rl"]["optimization_result"]["best_fitness"],
            "rl_best_params": results["rl"]["best_parameters"],
            "rl_miss_distance": results["rl"]["simulation_metrics"]["miss_distance"],
            "winner": "ga" if results["ga"]["simulation_metrics"]["miss_distance"] <
                        results["rl"]["simulation_metrics"]["miss_distance"] else "rl",
        }

        # Save comparison
        report_file = os.path.join(
            self.results_dir,
            f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)

        logger.info(f"Comparison complete. Winner: {comparison['winner']}")

        return comparison

    async def _optimize_with_optimizer(
        self,
        optimizer: BaseOptimizer,
        initial_params: GuidanceParameters,
        objectives: OptimizationObjectives,
        param_bounds: Dict[str, Tuple[float, float]],
        max_iterations: int,
    ) -> Dict[str, Any]:
        """使用指定优化器运行优化"""
        obj_dict = self._build_objective_dict(objectives)

        initial_dict = {
            "navigation_coefficient": initial_params.navigation_coefficient,
            "damping_ratio": initial_params.damping_ratio,
        }

        constraints = {}
        for name, (min_val, max_val) in param_bounds.items():
            constraints[name] = {"min": min_val, "max": max_val}

        opt_result = await optimizer.optimize(
            objectives=obj_dict,
            constraints=constraints,
            initial_params=initial_dict,
            max_iterations=max_iterations,
        )

        best_params = opt_result.best_parameters
        optimized_params = GuidanceParameters(
            navigation_coefficient=best_params.get("navigation_coefficient", 3.0),
            damping_ratio=best_params.get("damping_ratio", 0.3),
        )

        final_result = await self.simulator.executor.run_simulation(
            optimized_params, duration=100.0, dt=0.01
        )

        return {
            "optimizer": optimizer.name,
            "optimization_result": {
                "status": opt_result.status,
                "best_fitness": opt_result.best_fitness,
                "iterations": opt_result.iterations,
            },
            "best_parameters": best_params,
            "simulation_metrics": {
                "miss_distance": final_result.miss_distance,
                "control_energy": final_result.control_energy,
            },
        }


async def main():
    """运行示例优化"""
    print("=" * 60)
    print("Guidance System Optimization Workflow")
    print("=" * 60)

    # Create workflow
    workflow = GuidanceOptimizationWorkflow(
        output_dir="./guidance_optimization_output"
    )

    print(f"\nUsing optimizer: {workflow.optimizer.name}")
    print(f"Optimizer enabled: {workflow.config.optimizer.enabled}")

    # Define optimization
    initial_params = GuidanceParameters(
        navigation_coefficient=3.0,
        damping_ratio=0.3,
        control_gain=1.0,
        target_position=[20000.0, 2000.0, 5000.0],
        initial_position=[0.0, 7000.0, 0.0],
        initial_velocity=[960.0, 0.0, 0.0],
    )

    objectives = OptimizationObjectives(
        miss_distance=True,
        miss_distance_weight=1.0,
        control_energy=True,
        control_energy_weight=0.5,
    )

    param_bounds = {
        "navigation_coefficient": (0.3, 0.7),
        "damping_ratio": (0.2, 0.5),
    }

    # Run optimization
    print("\nRunning optimization...\n")
    result = await workflow.run_optimization(
        initial_params=initial_params,
        objectives=objectives,
        param_bounds=param_bounds,
        max_iterations=50,
    )

    # Print results
    print("\n" + "=" * 60)
    print("Optimization Results")
    print("=" * 60)
    print(f"Optimizer: {result['optimizer']}")
    print(f"Status: {result['optimization_result']['status']}")
    print(f"Iterations: {result['optimization_result']['iterations']}")
    print(f"\nBest Parameters:")
    for k, v in result['best_parameters'].items():
        print(f"  {k}: {v:.4f}")
    print(f"\nSimulation Metrics:")
    print(f"  Miss Distance: {result['simulation_metrics']['miss_distance']:.6f} m")
    print(f"  Control Energy: {result['simulation_metrics']['control_energy']:.6f} J")
    print(f"\nGenerated Files:")
    for cat, files in result['generated_files'].items():
        print(f"  {cat}:")
        for name, path in files.items():
            print(f"    - {name}")

    print("\n" + "=" * 60)
    print("Optimization Complete!")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    asyncio.run(main())
