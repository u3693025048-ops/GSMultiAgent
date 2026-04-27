# Multi-Agent Architecture

基于 **Hermes Agent** + **RAG** + **ParameterExperience** + **Simulation** 的多智能体系统。

## 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Hermes Agent (主Agent)                    │
│  ┌─────────────────────────────────────────────────────┐ │
│  │     IntelligentTaskPlanner (LLM智能任务规划)          │ │
│  └─────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────┐ │
│  │           SubagentManager (子Agent管理)                │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Base & Simulation               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ 知识库(模板)  │→ │ SysML/MATLAB │→ │  Octave仿真  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## 项目结构

```
multi_agent/
├── __init__.py                    # 包入口
├── config_loader.py                # 配置加载
├── integration/                    # Hermes Agent 集成
│   ├── hermes_integration.py       # Hermes 集成层
│   ├── task_planner.py             # 智能任务规划器
│   └── subagent.py                 # 子Agent管理
├── simulation/                     # 制导系统仿真模块
│   ├── guidance_simulator.py       # 仿真器核心（包含SysML/MATLAB生成与执行）
│   └── guidance_optimization_workflow.py  # 优化工作流
├── tools/                         # Hermes 兼容工具
│   ├── rag_tool.py               # RAG 检索/索引
│   ├── parameter_experience_tool.py               # ParameterExperience 记忆
│   ├── simulation_tool.py         # 仿真工具
│   └── optimization_tool.py       # 优化工具
├── memory/                         # 核心记忆模块
│   ├── parameter_experience.py                    # 动态记忆缓冲
│   └── rag_knowledge_base.py     # RAG 知识库
└── optimizers/                    # 优化算法
    ├── genetic_optimizer.py       # 遗传算法
    └── rl_optimizer.py           # 强化学习优化器

knowledge_base/                     # 统一知识库
├── matlab/                         # MATLAB 参考脚本 (鲁棒性分析/制导律等)
└── sysml/                          # SysML 参考模板与底层文档 (BDD/IBD/Parametric)

cli_agent.py                        # 命令行端到端工作流入口
run_complete_workflow.py            # 完整流程演示脚本
config.yaml                         # 配置文件
```

## 安装到运行

### 1. 环境准备

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. 安装依赖

```bash
# 安装 hermes-agent（主Agent）
pip install git+https://github.com/NousResearch/hermes-agent.git

# 安装基础依赖
pip install -r requirements.txt

# 安装 RAG 相关依赖（可选）
pip install chromadb sentence-transformers
```

### 3. 配置

config.yaml

### 4. 运行

```bash
# CLI 端到端执行（推荐）
# 此命令将执行一次完整的端到端工作流：
# 包含任务拆分、知识库读取、生成SysML模型、生成并运行MATLAB/Octave仿真、获取结果并反写到ParameterExperience。

# 方式一：直接传递 prompt 字符串
python cli_agent.py --prompt "分析不同导航系数(3.0, 4.0, 5.0)下的脱靶量，并给出最优推荐"

# 方式二：通过文件传递 prompt
python cli_agent.py --file prompt.txt

# 完整流程演示（用于理解框架执行逻辑）
python run_complete_workflow.py

```

## 核心功能

### 智能任务规划器

```python
from multi_agent import IntelligentTaskPlanner, smart_execute

planner = IntelligentTaskPlanner(hermes=hermes)

# 分析任务（LLM决策）
plan = await planner.analyze_and_plan("同时分析nav=0.3和nav=0.5")
# plan.should_split=True, plan.strategy=PARALLEL, plan.subagent_count=2

# 智能执行
result = await planner.execute("优化导航系数")
```

**决策策略**：

| 策略 | 说明 |
|------|------|
| `SINGLE` | 简单任务，不拆分 |
| `PARALLEL` | 并行任务，多子Agent执行 |
| `SEQUENTIAL` | 顺序任务，多子Agent执行 |

### Subagent 管理

```python
from multi_agent import SubagentManager, SubagentConfig

manager = SubagentManager(hermes)

# 单个子Agent
result = await manager.delegate(
    task="分析参数",
    config=SubagentConfig(name="analyzer", max_iterations=30),
)

# 并行多个子Agent
results = await manager.delegate_parallel(tasks=["任务1", "任务2", "任务3"])
```

### RAG 知识库 (ChromaDB)

```python
from multi_agent import RAGKnowledgeBase, EmbeddingConfig

# 配置 Embedding 模型
embedding_config = EmbeddingConfig(
    provider="local",  # "local", "openai", "custom"
    model="sentence-transformers/all-MiniLM-L6-v2",
)

# 初始化 RAG
rag = RAGKnowledgeBase()
await rag.initialize()

# 索引文档
await rag.index_documents([
    {"content": "导航系数范围 0.3-0.8", "metadata": {"topic": "guidance"}},
])

# 检索
results = await rag.retrieve("导航系数", top_k=5)

# 相似性搜索
results = await rag.similarity_search("制导优化", threshold=0.7)
```

### ParameterExperience 记忆

```python
from multi_agent import ParameterExperience, MemoryType

parameter_experience = ParameterExperience()

# 存储经验
await parameter_experience.store(
    task_context={"task": "optimization"},
    parameters={"nav": 0.5},
    objectives={"miss": 0.1},
    fitness=0.9,
    memory_type=MemoryType.LONG_TERM
)

# 搜索相似经验
results = await parameter_experience.retrieve_similar({"task": "optimization"}, top_k=5)
```

### 制导系统仿真与模型生成

本框架支持直接从 `knowledge_base` 读取参考模板与脚本，进行 SysML 模型生成与 MATLAB / Octave 仿真。

```python
from multi_agent.simulation import (
    GuidanceSimulator,
    GuidanceParameters,
)

# 配置参数
params = GuidanceParameters(
    navigation_coefficient=3.0,
    damping_ratio=0.3,
    target_position=[20000.0, 2000.0, 5000.0],
)

# 创建仿真器 (支持引擎: octave / matlab / python)
simulator = GuidanceSimulator(output_dir="./guidance_workspace", engine="octave")

# 运行仿真 (将基于知识库模板自动生成SysML BDD/IBD/Parametric文件并执行Octave仿真)
result = await simulator.generate_and_simulate(
    params=params,
    duration=100.0,
    dt=0.01,
    generate_sysml=True,   
    generate_matlab=True,  
)

# 参数研究
study_grid = {
    "navigation_coefficient": [0.3, 0.5, 0.7],
    "damping_ratio": [0.2, 0.3, 0.4],
}
results = await simulator.parameter_study(param_grid=study_grid)
```

**仿真输出**：

| 目录 | 内容 |
|------|------|
| `guidance_workspace/sysml/` | SysML 模型文件 (XML) |
| `guidance_workspace/matlab/` | MATLAB 脚本文件 (.m) |
| `guidance_workspace/results/` | 仿真结果 (JSON) |

### 完整优化工作流

```python
from multi_agent.simulation import GuidanceOptimizationWorkflow, GuidanceParameters, OptimizationObjectives

workflow = GuidanceOptimizationWorkflow(output_dir="./guidance_optimization_output")

# 定义初始参数
initial_params = GuidanceParameters(
    navigation_coefficient=0.5,
    damping_ratio=0.3,
    target_position=[10.0, 0.0],
)

# 定义优化目标
objectives = OptimizationObjectives(
    miss_distance=True,
    miss_distance_weight=1.0,
    control_energy=True,
    control_energy_weight=0.5,
)

# 运行优化
result = await workflow.run_optimization(
    initial_params=initial_params,
    objectives=objectives,
    param_bounds={
        "navigation_coefficient": (0.3, 0.7),
        "damping_ratio": (0.2, 0.5),
    },
    max_iterations=50,
)
```

## 配置文件说明

### config.yaml

```yaml
parameter_experience:
  enabled: true
  max_short_term: 100
  max_long_term: 1000
  similarity_threshold: 0.7
  decay_factor: 0.95

optimizer:
  enabled: true
  type: "ga"  # "ga" | "rl"

ga:
  population_size: 50
  crossover_rate: 0.8
  mutation_rate: 0.1
  max_generations: 100

rl:
  algorithm: "q_learning"
  learning_rate: 0.01
  discount_factor: 0.95
  epsilon: 0.1

knowledge_base:
  matlab_dir: "./knowledge_base/matlab"
  persist_dir: "./chroma_db"

simulation:
  engine: "octave"  # "python" | "octave" | "matlab"
  octave_path: "octave"
  matlab_path: "matlab"
```

## 工具清单

| 工具 | 功能 |
|------|------|
| `rag_retrieve` | 从知识库检索 |
| `rag_index` | 索引文档 |
| `parameter_experience_search` | 搜索相似经验 |
| `parameter_experience_store` | 存储经验 |
| `generate_sysml` | 生成 SysML 模型 |
| `generate_matlab` | 生成 MATLAB 脚本 |
| `run_simulation` | 运行仿真 |
| `parameter_study` | 参数研究 |
| `optimize_parameters` | 参数优化 |

## LLM 在架构中的作用

```
用户输入 → Hermes Agent (LLM) → 工具调用 → 结果聚合 → 回复
                              ↑
                      智能任务规划器
                      (LLM决策拆分/策略)
```

| 功能 | LLM负责 | 模块负责 |
|------|---------|---------|
| 理解意图 | ✅ | |
| 任务规划 | ✅ | |
| 工具选择 | ✅ | |
| 检索 | | RAG/ParameterExperience |
| 优化 | | RL |
| 仿真 | | Simulation |
| 子Agent执行 | | SubagentManager |

## License

MIT
