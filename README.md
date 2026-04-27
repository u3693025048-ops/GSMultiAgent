# GSMultiAgent —— 制导系统多智能体设计与优化框架

基于 **三层架构** + **monte_carlo_single.m 模板** + **PPO-RL** + **判断/反思智能体** 的制导律/自动驾驶仪协同设计与参数优化系统。

---

## 三层架构

```
┌────────────────────────────────────────────────────────────────────┐
│  LAYER 1  自然语言任务输入  (cli_agent.py)                          │
│  - 解析工况描述 → T/G/AP/R 类别映射                                │
│  - 解析性能要求 (命中率 / SEP / PeakNy / PM / BW)                  │
│  - 初始化全部组件，驱动 [Layer2→Layer3] 主迭代循环                  │
│  - 人工中断: Ctrl+C → 菜单（修改指令 / 晋升记忆 / 继续 / 退出）     │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  LAYER 2  Hermes Agent (任务分解 + 动态工具编排)                    │
│                                                                    │
│  工具集 (9个，LLM 动态编排):                                        │
│  ① rag_retrieve              统一检索知识库 + 经验库               │
│  ② parameter_experience_best 获取历史最优参数                       │
│  ③ generate_matlab           生成 .m 脚本 (monte_carlo_single)     │
│  ④ generate_sysml            生成 SysML BDD/IBD 模型               │
│  ⑤ syntax_check_matlab       语法校正 .m 文件                       │
│  ⑥ run_simulation            运行 monte_carlo_single 仿真           │
│  ⑦ judge_requirements        判断仿真指标是否满足任务要求            │
│  ⑧ extract_matlab_params     从脚本提取参数值                       │
│  ⑨ parameter_experience_search 搜索相似历史参数                    │
│                                                                    │
│  三种设计模式（通用流程规则）:                                       │
│  ┌─ REUSE_HISTORY: rag→pe_best→run_simulation ──────────────────┐ │
│  │  TUNE_PARAMS:   rag→pe_best→generate_matlab→[校正]→仿真       │ │
│  │  MODIFY_LAW:    rag→sysml→generate_matlab→[校正]→仿真         │ │
│  │                                                               │ │
│  │  [校正] generate_matlab 后必须先 syntax_check_matlab          │ │
│  │  [出错] run_simulation 报错 → syntax_check_matlab → 重仿真    │ │
│  └───────────────────────────────────────────────────────────── ┘ │
│                                                                    │
│  仿真成功后 → judge_requirements → 两条出口:                        │
│  ── satisfied=True  → 跳过 RL，直接进 Layer3 反思 → 经验回写 ────  │
│  ── satisfied=False → 进入 Layer3 RL 参数优化环节 ───────────────  │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ script_path + initial_metrics
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  LAYER 3  优化工作流  (optimization_workflow.py, async)             │
│                                                                    │
│  ┌───────────────────┐    每 episode     ┌──────────────────────┐  │
│  │  RL优化器          │ ←──────────────→ │  判断智能体           │  │
│  │  PPO, 调9参数:     │   新最优时触发    │  JudgmentAgent       │  │
│  │  w1,zeta1,tao1    │                  │  规则检查→早退出      │  │
│  │  w2,zeta2,tao2    │                  │  (规则通过才调LLM)    │  │
│  │  w3,zeta3, N_pn   │                  └──────────────────────┘  │
│  │  (patch RL_PARAMS │                                            │
│  │   块 in .m 文件)   │                                            │
│  └────────┬──────────┘                                            │
│           │ 满足/达最大轮数                                         │
│           ▼                                                        │
│  反思智能体 (ReflectionAgent) — LLM 深度分析                        │
│           │                                                        │
│     满足  │  不满足                                                 │
│     ▼     │  ▼                                                     │
│  经验回写  │  优化建议 → 返回 Layer1                                 │
│  (params  │  next_action: tune_params / modify_law                 │
│  + model) │                                                        │
│     ▼                                                              │
│  仿真报告 (JSON + MD)                                               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
GSMultiAgent/
├── cli_agent.py                         # 端到端 CLI 入口（Layer1）
├── config.yaml                          # 运行配置（LLM / RAG / RL / 工况）
├── prompt.txt                           # 任务描述示例
├── requirements.txt
│
├── multi_agent/                         # 核心包
│   ├── config_loader.py                 # 统一配置加载
│   │
│   ├── integration/                     # Layer2+3 智能体
│   │   ├── hermes_integration.py        # Hermes 初始化、工具注入 [Layer2]
│   │   ├── task_planner.py              # 智能任务规划器 (LLM 语义分析)
│   │   ├── judgment_agent.py            # 判断智能体 (Layer3 每 episode 评估) [NEW]
│   │   ├── reflection_agent.py          # 反思智能体 (LLM 深度分析)
│   │   └── subagent.py                  # 子 Agent 并行/顺序管理
│   │
│   ├── simulation/                      # 仿真模块
│   │   ├── optimization_workflow.py     # Layer3 异步工作流 [NEW]
│   │   └── guidance_simulator.py        # Octave/MATLAB 执行引擎
│   │
│   ├── rl/                              # 强化学习模块
│   │   └── matlab_rl_optimizer.py       # PPO 8维参数优化 (T/G/AP/R 工况)
│   │
│   ├── memory/                          # 记忆模块
│   │   ├── parameter_experience.py      # 参数经验库（短/长期）
│   │   └── rag_knowledge_base.py        # ChromaDB + Embedding 检索
│   │
│   └── tools/                           # Layer2 Hermes 工具
│       ├── rag_tool.py                  # rag_retrieve
│       ├── parameter_experience_tool.py # pe_search / pe_best
│       ├── simulation_tool.py           # generate_matlab / run_simulation
│       ├── syntax_check_tool.py         # syntax_check_matlab [NEW]
│       ├── judge_requirements_tool.py   # judge_requirements  [NEW]
│       └── matlab_rl_tool.py            # matlab_rl_optimize
│
├── knowledge_base/                      # 模板知识库（RAG 源）
│   ├── matlab/guidance/
│   │   └── monte_carlo_single.m         # 主仿真模板 (T/G/AP/R 工况)
│   ├── conditions.md                    # 工况体系说明
│   └── sysml/                           # SysML BDD/IBD/Parametric 模板
│
├── parameter_experience_base/           # 参数经验持久化
│   ├── params/  (JSON)
│   └── models/  (成功模型 .m 副本)
│
└── guidance_output/
    ├── models/                          # Layer2 生成的脚本
    ├── reports/                         # Layer3 生成的 JSON 报告
    └── sysml/                           # SysML 输出
```

---

## 独立优化工具（无需 LLM）

提供四种独立优化脚本，直接对 MATLAB 仿真脚本进行参数优化，**不依赖 Hermes / LLM**。

| 脚本 | 算法 | 每轮仿真数 | 结果目录 |
|------|------|:----------:|---------|
| `run_rl_optimize.py` | PPO 强化学习 | 1 | `./rl_results/` |
| `run_ga_optimize.py` | 遗传算法 (GA) | pop_size (默认 20) | `./ga_results/` |
| `run_pso_optimize.py` | 粒子群 (PSO) | swarm_size (默认 20) | `./pso_results/` |
| `run_sa_optimize.py` | 模拟退火 (SA) | 1 | `./sa_results/` |

所有脚本支持三种运行模式（指标驱动 / 轮次驱动 / 双约束）、8 维参数优化、工况选择、指标要求（`--hitrate` / `--missmean` / `--peak-n` / `--pm`）。

> 📄 **详细文档** → [`OPTIMIZERS.md`](./OPTIMIZERS.md)（算法原理、流程、完整参数列表、典型用法、算法对比）

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt
pip install git+https://github.com/NousResearch/hermes-agent.git

# 方式一：命令行传入任务
python cli_agent.py --prompt "目标机动工况，要求命中率>=90%，SEP脱靶量<=5m，PM相位裕度在范围内"

# 方式二：从文件读入
python cli_agent.py --file prompt.txt
`IntelligentTaskPlanner` 由 **Hermes Agent 的任务分析**决定执行模式，而非用户提示词关键字匹配。关键词启发式仅作为 LLM 提示偏置，**最终模式由 LLM 对任务需求的语义理解决定**。

| 模式 | 选择条件（任务需求） | Hermes 执行方式 |
|------|---------------------|-----------------|
| **REUSE_HISTORY** *(默认)* | 任务核心是仿真/验证，未要求改参数或改算法，历史参数已足够 | **直接调用 KB 模板仿真**（不生成新脚本）+ PPO-RL 在 KB 模板上优化 8 维参数 |
| **TUNE_PARAMS** | 任务明确要改善性能（命中率/脱靶量/稳定裕度），需要调整制导律或驾驶仪参数 | 生成新脚本 → PPO-RL 同时调优**制导律参数**和**驾驶仪参数**（8维）|
| **MODIFY_LAW** | 任务要求设计新制导算法（改变数学结构，非调参） | 修改制导律算法本身 → 生成新 MATLAB 文件 |

> ❗ **模式与关键词无关**，由 Hermes Agent 对任务的语义理解决定。"运行工况"(run_A/sub_A) 只表示选择哪些工况，不影响模式。

**REUSE_HISTORY 执行路径**：
1. Step 2.5 (Hermes)：`parameter_experience_best` → `run_simulation(script_path=KB_TEMPLATE, dp_params=历史最优)` → 基线仿真结果（不生成新脚本）
2. Step 3 (自动)：PPO-RL 直接在 KB 模板上优化 8 维参数（8 驾驶仪 + 0 制导律）

KB 模板文件本身不被修改；RL 在内存 patch 参数后写临时文件运行，运行完自动删除。

TUNE_PARAMS 可调参数一览：

| 类别 | 参数名 | 含义 | 范围 | 默认值 |
|------|--------|------|------|--------|
| 驾驶仪 | `w1` | 俑仰通道带宽 | 5–25 | 14 |
| 驾驶仪 | `zeta1` | 俑仰通道阻尼比 | 0.3–1.2 | 0.75 |
| 驾驶仪 | `w2` | 偏航通道带宽 | 5–22 | 12 |
| 驾驶仪 | `zeta2` | 偏航通道阻尼比 | 0.3–1.2 | 0.75 |
| 驾驶仪 | `w3` | 滚转通道带宽 | 5–25 | 14 |
| 驾驶仪 | `zeta3` | 滚转通道阻尼比 | 0.3–1.2 | 0.7 |
| 制导律 | `N_pn` | 导引比 | 2.0–6.0 | 4.0 |
| 制导律 | `sw_dist` | 切换距离 (m) | 3000–12000 | 7000 |

---

## 任务工况体系（T/G/AP/R）

`monte_carlo_single.m` 定义四类工况，通过 `RUN_CASE` + `SUB_IDX` 选择：

| RUN_CASE | 名称 | 子工况 |
|---------|------|------|
| **T** | 目标机动 | T1:匀速直飞, T2:低频小幅, T3:中频中等, T4:高频大幅 |
| **G** | 交战几何 | G1:标称几何, G2:近距小偏, G3:近距大偏, G4:远距小偏, G5:远距大偏 |
| **AP** | 驾驶仪退化 | AP1:全标称, AP2:时间常数退化, AP3:轻度退化, AP4:中度退化, AP5:重度退化 |
| **R** | 综合鲁棒 | R1:全标称, R2:多参数摄动, R3:大姿态偏差 |
| **ALL** | 全工况 | 依次运行 T/G/AP/R |

提示词示例：“目标机动工况”→ `RUN_CASE='T';SUB_IDX=0;`，“全工况”→ `RUN_CASE='ALL';`

---

## PPO 强化学习参数优化

`MatlabRLOptimizer`（`multi_agent/rl/matlab_rl_optimizer.py`）对 **monte_carlo_single.m 的 RL_PARAMS 块** 进行 8 维 PPO 优化：

**动作空间**（8 维连续）：
| 类别 | 参数 |
|------|------|
| 驾驶仪 | `w1`、`zeta1`、`w2`、`zeta2`、`w3`、`zeta3` |
| 制导律 | `N_pn`、`sw_dist` |

**奖励函数**（综合脱靶量 / 命中率 / 稳定裕度 / 控制能量 / 终端角误差）：
```
reward = 3.0*hit_rate + miss_bonus + PM_bonus + GM_bonus - energy_penalty - angle_penalty
```

**反思智能体作为唯一早停决策者**：每个 episode 出现新最优时调用反思智能体，综合判定**用户提的所有任务要求**是否同时满足：

| 触发条件 | 退出状态 | 说明 |
|---------|----------|------|
| `ReflectionAgent.reflect(prompt, metrics)` 返回 `needs_optimization=False` | `task_requirements_met` | 用户全部要求（PM/GM/命中率/脱靶量/控制能量/…）已满足 |
| 跑满 `max_episodes` 仍未满足 | `success` | 自然结束，输出当前最优 |

两种状态均会持久化最优参数到 ParameterExperience。`task_requirements_met` 还会跳过 Step 3.5 多余的 LLM 反思调用直接进入 Step 4。

**重要变更**：之前版本支持的 `miss_threshold` 硬阈值早停已**移除**。脱靶量阈值过于片面（只看单一指标），无法体现用户综合要求（例如"PM>30°、命中率>80%、脱靶量<5m"），现统一交由反思智能体做语义级综合判断。`miss_threshold` 参数仍保留，但仅作为**信息性 hint** 转发给反思智能体作为额外上下文。

**仿真执行优先级**：
1. Octave / MATLAB 运行脚本（内存 patch dp.* 参数 → 临时文件 → 执行 → 解析 stdout）
2. Python 内置解析仿真（Octave/MATLAB 不可用时回退，8 维参数均有效）

**Hermes 工具调用支持** — `matlab_rl_optimize` 工具：
- `task_prompt` — 用户任务原文。**Hermes 模式下由 `HermesIntegration.initialize_with_tools(user_prompt=...)` 自动注入**，LLM 无需手动转发
- `reflect_every` — 反思调用频次（默认 1，每个新最优都调一次）
- `miss_threshold` — 信息性数值 hint（不再触发早停）

返回 `task_requirements_met` 字段告知 Hermes 早停原因，便于其继续保存模型 + 生成报告。

**典型日志**：
```
[Ep 3/30] reward=2.821  hit=85.0%  miss=2.94m  best_miss=2.94m  PM=38.2°
[RL Reflection @ Ep 3] needs_optimization=False | 已满足脱靶量<5m且PM>30°要求
[RL] Task requirements met per reflection at episode 3; early exit.
✓ RL early-stopped: task requirements met per reflection (after 3 episodes)
```

---

## 反思智能体（Reflection Agent）

`ReflectionAgent`（`multi_agent/integration/reflection_agent.py`）在系统中承担**双重职责**：

### 角色 1：RL 循环内的任务要求判定（Step 3 的一部分）

每当 RL 出现新最优参数时，反思智能体被调用以决定**用户的完整任务要求**是否已经满足（不仅仅是脱靶量）：

```
RL Episode N (出现新最优):
   ├─ Optimizer 内部调用 ReflectionAgent.reflect(task_prompt, best_metrics)
   ├─ 输入: 用户原始 prompt + 当前最优 {miss, hit, PM, GM, BW, control_energy, …}
   └─ 返回: { needs_optimization: bool, suggestion: str }
         ✓ False → RL 立即 break，status="task_requirements_met"，回写参数
         ✗ True  → 继续训练，suggestion 仅记录到日志
```

通过 `cli_agent.py` 自动启用，或 Hermes 调用 `matlab_rl_optimize` 时显式传入 `task_prompt` 启用。

### 角色 2：迭代外层的反思判别（Step 3.5）

仅当 RL 没有早停时（`status="success"`）才执行：

```
Step 3.5
  ├─ rl_status == "task_requirements_met"? ✓ → 跳过反思直接 → Step 4
  └─ 否则 → ReflectionAgent.reflect(prompt, best_result)
              ✓ needs_optimization=True  + 未达 max_iterations
                  → continue（建议拼接到下轮 Hermes 提示词）
              ✗ needs_optimization=False → break → Step 4
```

### 鲁棒性
- 已对 `asyncio.CancelledError` 做健壮处理，LLM 异常不中断 RL 训练或主流程
- RL 内反思调用失败仅打 `WARNING` 日志，继续训练
- 默认 `reflect_every=1`（每个新最优都判定一次），可通过 Hermes 工具参数调高以降低 LLM 成本

---

## 配置文件说明

`config.yaml`（与 `config.copy.yaml` 模板一致）：

```yaml
llm:
  provider: openrouter              # openai | anthropic | openrouter | custom
  base_url: https://openrouter.ai/api/v1
  model:    anthropic/claude-sonnet-4.6
  api_key:  <your key>              # 也可通过 .env / env var 提供

rag:
  persist_dir:        ./chroma_db
  collection:         knowledge_base
  embedding_provider: local         # local | openai | openrouter | custom
  embedding_model:    sentence-transformers/all-MiniLM-L6-v2
  embedding_dim:      384

knowledge_base:
  matlab_dir: ./knowledge_base/matlab

simulation:
  engine:      octave               # octave | matlab | python
  octave_path: octave
  matlab_path: matlab

workflow:
  max_iterations:    3              # 外层迭代次数
  hermes_execution:  true

matlab_rl_optimizer:
  max_episodes:  30                 # PPO 回合数
  nmc_per_eval:  20                 # 每次评估的蒙特卡洛次数
  hidden_dim:    64
  lr_actor:      3.0e-4
  lr_critic:     1.0e-3
  gamma:         0.99

model_output:
  generated_dir:      ./parameter_experience_base/models
  experience_base_dir: ./parameter_experience_base
  matlab_scripts_dir: ./matlab_scripts
  sysml_output_dir:   ./guidance_output/sysml

reflection_agent:
  enabled: true
```

---

## Layer 2 工具清单（Hermes Tools）

> RL 优化完全由 **Layer 3 OptimizationWorkflow** 执行，`matlab_rl_optimize` 已从 Hermes 工具集移除。

| 工具名 | 功能 |
|--------|------|
| `rag_retrieve` | 统一检索知识库 + 经验库（模型+参数） |
| `generate_matlab` | 生成 .m 脚本（monte_carlo_single 模板，含 RL_PARAMS 块） |
| `generate_sysml` | 生成 SysML BDD/IBD 模型 |
| `syntax_check_matlab` | 验证并自动修复 .m 文件（RL_PARAMS 块检查）|
| `run_simulation` | 运行 monte_carlo_single 仿真，输出命中率/SEP/PeakNy/PM/BW |
| `judge_requirements` | 判断仿真指标是否满足任务要求，满足则跳过 Layer3 RL |
| `parameter_experience_best` | 获取历史最优参数 |
| `parameter_experience_search` | 搜索相似历史参数 |
| `extract_matlab_params` | 从 .m 脚本提取参数值 |

---

## 快速使用片段

### 完整三层流程

```bash
python cli_agent.py --prompt "目标机动工况T2，要求命中率>=90%，SEP<=3m，PM在30~60度"
```

### 直接调用 Layer3 工作流

```python
from multi_agent.simulation.optimization_workflow import OptimizationWorkflow
from multi_agent.rl.matlab_rl_optimizer import MatlabRLOptimizer
from multi_agent.integration.judgment_agent import JudgmentAgent
from multi_agent.integration.reflection_agent import ReflectionAgent
from multi_agent.simulation import GuidanceSimulator

simulator  = GuidanceSimulator(engine="matlab_engine")
reflection = ReflectionAgent()
judgment   = JudgmentAgent(reflection_agent=reflection,
                           task_prompt="命中率>=90%，SEP<=3m，PM在30~60度")

workflow = OptimizationWorkflow(
    rl_optimizer=MatlabRLOptimizer(simulator=simulator, max_episodes=20),
    judgment_agent=judgment,
    reflection_agent=reflection,
)

result = await workflow.run(
    script_path="./knowledge_base/matlab/guidance/monte_carlo_single.m",
    task_prompt="目标机动工况，命中率>=90%，SEP<=3m，PM在30~60度",
    mission_conditions={"T": [0, 1, 2, 3]},  # T类全部子工况
)
print(result["status"])        # "done" 或 "needs_iteration"
print(result["best_metrics"])  # hit_rate, SEP, peak_ny, pitch_PM, pitch_BW
```

### RAG 检索

```python
from multi_agent import RAGKnowledgeBase

rag = RAGKnowledgeBase()
await rag.initialize()
await rag.index_directory("./knowledge_base", patterns=[".md", ".txt", ".m"])

results = await rag.retrieve("pitch autopilot PM GM margin", top_k=3)
for r in results:
    print(r["score"], r["metadata"]["filename"])
```

---

## 已知问题与设计决策

- **Octave / MATLAB 未安装时**：RL 自动回退到 Python 解析型仿真（11 维参数均有效），不阻塞训练
- **LLM 返回空响应或非 JSON**：TaskPlanner 默认返回 `REUSE_HISTORY` 计划（最安全的无副作用路径）
- **反思调用被取消**：`reflect()` 捕获 `CancelledError`，返回 `needs_optimization=False`，不中断主流程
- **Hermes auxiliary client 警告** (`custom/main no endpoint credentials`)：`hermes_integration.py` 在初始化前自动注入 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 环境变量解决
- **Octave 绘图兼容性**：模板中 `legend 'best'` → `'northeast'`；`errorbar` 移除不支持的 `LineWidth` 命名参数
- **模板参数化**：`dp.N_guidance`、`dp.R_switch`、`dp.gama_max_deg` 已在两个 MATLAB 模板中显式声明，供 RL patch
- **`roots: inputs must not contain Inf or NaN`**：当 RL 探索到极端参数时，三回路驾驶仪设计矩阵可能产生 Inf/NaN 系数，进而导致 `margin()` → `roots()` 崩溃。两个模板中现已加入：
  - `safe_coef()` / `safe_coef_local()` 辅助函数 — 在构造 `tf()` 前清洗 Inf/NaN 系数
  - `extract_margins()` / `get_margin_metrics_local()` 全部加 `try/catch` + 系数预检查；失败时返回 `NaN` 不崩溃

---

## LLM 在架构中的职责边界

| 功能 | LLM 负责 | 模块负责 |
|------|:--------:|---------|
| 理解任务意图 | ✅ | |
| 任务模式选择（语义分析） | ✅ **唯一决策者** | 关键词仅作后备 fallback |
| 工具调用编排 | ✅ | Hermes Agent |
| 反思与优化建议 | ✅ | |
| SysML / MATLAB 模板 | | `knowledge_base/` + `generate_*` |
| 参数检索 | | RAG / ParameterExperience |
| 参数优化 | | PPO (`MatlabRLOptimizer`, 11维) |
| 脱靶量阈值判断 | | `cli_agent.py` + `MatlabRLOptimizer` |
| 仿真执行 | | `GuidanceSimulator` / Octave/MATLAB |
| 子任务并行/顺序 | | `SubagentManager` |

---

## 替换仿真模板程序指南

当需要将 `monte_carlo_single.m` 替换为其他 MATLAB/Octave 仿真脚本时，需同步修改以下文件。

### 1. 新模板文件本身

**位置**：`knowledge_base/matlab/guidance/<new_template>.m`

必须满足以下约定，程序才能自动 patch 和解析：

```matlab
%% ── RL_PARAMS_BEGIN (auto-patched by RL optimizer, do not edit manually) ──
rl_w1    = 40;      % 需要 RL 优化的参数以 rl_ 开头
rl_zeta1 = 0.75;
rl_tao1  = 0.20;
% ... 其他 rl_* 参数 ...
%% ── RL_PARAMS_END ──
```

- RL optimizer 仅修改 `RL_PARAMS_BEGIN` 到 `RL_PARAMS_END` 之间的 `rl_*` 变量
- 模板其余部分不会被自动修改

**输出格式**（stdout 供 Python 解析，须包含以下字段之一）：
```
命中率(miss<10m): 92.5%  SEP: 4.23m
峰值法向过载: 15.3g
俯仰PM: 52.1°  BW: 16.8 rad/s
```
如输出格式不同，需同步修改 `matlab_rl_optimizer.py` 中的 `_parse_simulation_output()`。

---

### 2. RL 优化参数空间 — `matlab_rl_optimizer.py`

**文件**：`multi_agent/rl/matlab_rl_optimizer.py`，约第 30–80 行

修改两个 Spec 字典和一个映射表：

```python
# 驾驶仪参数（RL 可调范围 + 标称值）
AUTOPILOT_PARAM_SPECS = {
    "w1":    ParameterSpec(20.0, 60.0, 40.0),   # 按新模板调整范围
    "zeta1": ParameterSpec(0.3,  1.2,  0.75),
    # ...新增或删除参数...
}

# 制导律参数
GUIDANCE_PARAM_SPECS = {
    "N_pn": ParameterSpec(2.0, 6.0, 4.0),
    # ...
}

# Python 参数名 → MATLAB rl_* 变量名（须与模板 RL_PARAMS_BEGIN 块对应）
RL_PARAM_TO_MATLAB = {
    "w1":    "rl_w1",
    "zeta1": "rl_zeta1",
    # ...
}
```

若新模板的**输出指标**不同（如新增/删除某个指标），还需修改同文件中的 `_compute_reward()` 奖励函数。

---

### 3. 工况子类别定义 — `matlab_rl_optimizer.py`

同文件约第 240–255 行的 `CATEGORY_DEFS`，将工况分类改为新模板的分类体系：

```python
CATEGORY_DEFS: Dict[str, Dict] = {
    "T": {"name": "目标机动", "max_sub": 4,
          "subcases": {0: "T1:匀速直飞", 1: "T2:低频", ...}},
    # 按新模板工况体系修改
}
```

同时检查同文件的 `build_matlab_conditions_str()` 函数，确认 `RUN_CASE` / `SUB_IDX` 注入字符串格式与新模板一致。

---

### 4. 知识库文件 — `knowledge_base/`

| 文件 | 修改内容 |
|------|---------|
| `conditions.md` | 将工况分类（T/G/AP/R）、子工况编号及其物理含义改为新模板的工况体系 |
| `monte mean results.md` | 将基准仿真结果（命中率/SEP/PeakNy/PM/BW）替换为新模板跑出的结果 |
| `expert design path.md` | （可选）更新专家设计路径建议，与新模板匹配 |

这三个文件由 RAG 检索后注入 LLM 提示词，直接影响任务规划器的工况分析和经验复用判断。

---

### 5. 任务规划器提示词 — `task_planner.py`

**文件**：`multi_agent/integration/task_planner.py`，`analyze_mission_conditions()` 中的 `gk_prompt` 字符串（约第 295–315 行）

将子工况描述改为新体系：

```python
"  • T：目标机动(T1 匀速直飞/T2 低频小幅/...)\n"
"  • G：交战几何(G1 标称/G2 近距/...)\n"
# 按新模板修改，与 conditions.md 保持一致
```

---

### 6. 仿真工具路径 — `simulation_tool.py`

**文件**：`multi_agent/tools/simulation_tool.py`，`RunSimulationTool.execute()`

默认优先使用 `matlab_scripts_dir` 中最新生成的脚本；若需要固定使用某个新模板作为默认，修改以下优先级逻辑中的 KB 模板文件名：

```python
# 约第 1230–1250 行，搜索 "monte_carlo_single"
_kb_template = Path(kb_dir) / "guidance" / "monte_carlo_single.m"
# 改为新模板文件名：
_kb_template = Path(kb_dir) / "guidance" / "<new_template>.m"
```

---

### 7. 配置文件 — `config.yaml`

```yaml
simulation:
  engine: octave           # octave | matlab | python — 不变，取决于运行环境

rl_optimizer:
  # 按新模板指标含义调整奖励权重
  reward_weights:
    hit_rate: 3.0
    sep_penalty: 1.0
    peak_ny_penalty: 0.5
    pm_bonus: 1.0
    bw_bonus: 0.5
  # 调整判断门限
  thresholds:
    hit_rate_min: 92.0     # %
    sep_max:      7.0      # m
    peak_ny_max:  20.0     # g
    pm_min:       45.0     # °
    pm_max:       65.0     # °
    bw_min:       12.0     # rad/s
    bw_max:       22.0     # rad/s
```

---

### 8. 任务提示词 — `prompt.txt`

将工况指定改为新模板的工况格式：

```
运行工况: RUN_CASE='<新类别>'; SUB_IDX=<子工况序号>;
```

---

### 快速核对清单

| # | 文件 | 检查点 |
|---|------|--------|
| 1 | 新 `.m` 模板 | `RL_PARAMS_BEGIN/END` 块存在，`rl_*` 变量与 Python Spec 对应 |
| 2 | 新 `.m` 模板 | stdout 输出含命中率/SEP/PeakNy/PM/BW 字样（或修改 parser）|
| 3 | `matlab_rl_optimizer.py` | `AUTOPILOT_PARAM_SPECS`、`GUIDANCE_PARAM_SPECS`、`RL_PARAM_TO_MATLAB` 三者一致 |
| 4 | `matlab_rl_optimizer.py` | `CATEGORY_DEFS` 工况编号与新模板 `SC{}` 数组一致 |
| 5 | `conditions.md` | 子工况编号与物理含义与新模板一致 |
| 6 | `monte mean results.md` | 基准结果来自新模板实际运行 |
| 7 | `task_planner.py` | LLM prompt 中子工况描述与 `conditions.md` 同步 |
| 8 | `simulation_tool.py` | KB 模板默认路径指向新文件 |
| 9 | `config.yaml` | 奖励权重和指标门限与新模板输出量纲匹配 |
| 10 | `prompt.txt` | `RUN_CASE` / `SUB_IDX` 格式与新模板一致 |

---

## License

MIT
