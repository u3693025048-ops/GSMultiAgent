# GSMultiAgent —— 制导系统多智能体设计与优化框架

基于 **三层架构** + **子智能体编排** + **PPO-RL 参数优化** + **判断/反思智能体** 的制导律与自动驾驶仪协同设计系统。以 `monte_carlo_single.m` 为仿真模板，支持 T/G/AP/R 四类工况的蒙特卡洛评估。

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
│  LAYER 2  Hermes Agent（纯编排器 + 子智能体委托）                   │
│                                                                    │
│  编排方式：                                                         │
│  ① 直接调用工具（直接模式）                                         │
│  ② call_specialist(agent_type, task, context) 委托子智能体           │
│                                                                    │
│  五类专用子智能体（各自工具隔离，防递归）:                           │
│  ┌ rag_agent      → rag_query / rag_retrieve / rag_expand          │
│  ├ matlab_agent   → generate_matlab / syntax_check / compat_verify │
│  ├ sim_agent      → run_simulation / syntax_check_matlab           │
│  ├ analysis_agent → judge_requirements / parameter_experience_*    │
│  └ memory_agent   → agent_memory_remember/recall/list/forget       │
│                                                                    │
│  MODIFY_LAW 推荐委托流程:                                           │
│  rag_agent → matlab_agent → sim_agent → analysis_agent             │
│  （每步 JSON 输出作为下步 context 传入）                            │
│                                                                    │
│  仿真成功后 → judge_requirements → 两条出口:                        │
│  ── satisfied=True  → 跳过 RL，直接进 Layer3 反思 → 经验回写        │
│  ── satisfied=False → 进入 Layer3 RL 参数优化环节                   │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ script_path + initial_metrics
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  LAYER 3  优化工作流  (optimization_workflow.py, async)             │
│                                                                    │
│  ┌──────────────────┐    每 episode     ┌─────────────────────┐   │
│  │  PPO-RL 优化器    │ ←──────────────→ │  判断智能体          │   │
│  │  9 维参数:        │   新最优时触发    │  ReflectionAgent    │   │
│  │  w1,zeta1,tao1   │                  │  规则检查→早退出     │   │
│  │  w2,zeta2,tao2   │                  │  (规则通过才调LLM)   │   │
│  │  w3,zeta3, N_pn  │                  └─────────────────────┘   │
│  └────────┬─────────┘                                             │
│           │ 满足 / 达最大轮数                                       │
│           ▼                                                        │
│  反思智能体 (ReflectionAgent) — LLM 深度分析                        │
│     满足 → 经验回写 (params + model) → 仿真报告 (JSON)              │
│     不满足 → 优化建议 → 返回 Layer1 (tune_params / modify_law)      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
GSMultiAgent/
├── cli_agent.py                         # 端到端 CLI 入口（Layer1）
├── config.yaml                          # 运行配置（LLM / RAG / RL / 消融开关）
├── prompt.txt                           # 任务描述示例
├── requirements.txt
│
├── multi_agent/                         # 核心包
│   ├── config_loader.py                 # 统一配置加载
│   │
│   ├── integration/                     # Layer2+3 智能体
│   │   ├── hermes_integration.py        # Hermes 初始化、工具注入 [Layer2]
│   │   ├── sub_agent.py                 # 专用子智能体（工具过滤器模式）
│   │   ├── task_planner.py              # 智能任务规划器 (LLM 语义分析)
│   │   ├── judgment_agent.py            # 判断智能体 (Layer3 每 episode 评估)
│   │   ├── reflection_agent.py          # 反思智能体 (LLM 深度分析)
│   │   └── subagent.py                  # 子 Agent 并行/顺序管理
│   │
│   ├── simulation/                      # 仿真模块
│   │   ├── optimization_workflow.py     # Layer3 异步工作流
│   │   └── guidance_simulator.py        # Octave/MATLAB 执行引擎
│   │
│   ├── rl/                              # 强化学习模块
│   │   └── matlab_rl_optimizer.py       # PPO 9维参数优化 (8驾驶仪+N_pn)
│   │
│   ├── memory/                          # 记忆模块
│   │   ├── parameter_experience.py      # 参数经验库（短/长期）
│   │   ├── hermes_agent_memory.py       # Hermes 持久记忆 (JSON KV)
│   │   └── rag_knowledge_base.py        # ChromaDB + Embedding 检索
│   │
│   └── tools/                           # Layer2 Hermes 工具
│       ├── rag_tool.py                  # rag_query / rag_retrieve / rag_expand
│       ├── parameter_experience_tool.py # parameter_experience_best/search
│       ├── simulation_tool.py           # generate_matlab / run_simulation
│       ├── syntax_check_tool.py         # syntax_check_matlab
│       ├── judge_requirements_tool.py   # judge_requirements
│       ├── compatibility_tool.py        # verify_guidance_compat (数学适配性)
│       ├── memory_tools.py              # agent_memory_remember/recall/list/forget
│       └── delegate_tool.py             # call_specialist (子智能体委托)
│
├── knowledge_base/                      # 模板知识库（RAG 源）
│   ├── matlab/guidance/
│   │   └── monte_carlo_single.m         # 主仿真模板 (T/G/AP/R 工况)
│   ├── conditions.md                    # 工况体系说明
│   ├── expert design path.md            # 专家设计路径建议
│   └── monte mean results.md            # 基准仿真结果
│
├── parameter_experience_base/           # 参数经验持久化（跨任务保留）
│   ├── params/short_term / long_term    # 参数 JSON
│   └── models/short_term / long_term    # 通过验收的模型 .m 副本
│
└── guidance_output/
    ├── scripts/                         # Layer2/3 生成脚本
    └── reports/                         # Layer3 JSON 报告
```

---

## 快速开始

```bash
# 创建并激活虚拟环境 (Windows)
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 可选：Layer 2 Hermes 编排（提供 run_agent；无此包时 CLI 仍可导入并完成 Step 1）
pip install git+https://github.com/NousResearch/hermes-agent.git

# 方式一：命令行传入任务
.\.venv\Scripts\python.exe cli_agent.py --prompt "交战几何G3工况，要求命中率>=92%，SEP<=7m，PM在45°~65°"

# 方式二：从文件读入
python cli_agent.py --file prompt.txt
```

> 编辑 `config.yaml` 设置 LLM provider/model/api_key 和仿真引擎（octave/matlab）。

---

## 设计模式

`IntelligentTaskPlanner` 由 **Hermes Agent 的语义分析**决定执行模式（非关键词匹配）：

| 模式 | 选择条件 | Layer2 执行方式 |
|------|---------|----------------|
| **REUSE_HISTORY** | 历史参数已足够，无需改算法或重新调参 | 直接用 KB 模板 + 历史最优 `dp_params` 仿真 |
| **TUNE_PARAMS** | 需改善性能，调整驾驶仪/制导律参数 | 生成新脚本 → 校正 → 仿真 |
| **MODIFY_LAW** | 需设计新制导算法（改数学结构） | rag_agent → matlab_agent → sim_agent → analysis_agent |

**TUNE_PARAMS / REUSE_HISTORY 可调参数（RL 优化 9 维）：**

| 类别 | 参数 | 含义 | 默认值 |
|------|------|------|--------|
| 驾驶仪 | `w1`, `zeta1`, `tao1` | 俯仰通道带宽/阻尼/时间常数 | 40, 0.75, 0.20 |
| 驾驶仪 | `w2`, `zeta2`, `tao2` | 偏航通道带宽/阻尼/时间常数 | 35, 0.75, 0.20 |
| 驾驶仪 | `w3`, `zeta3` | 滚转通道带宽/阻尼 | 30, 0.70 |
| 制导律 | `N_pn` | 比例导引比 | 4.0 |

---

## 任务工况体系（T/G/AP/R）

`monte_carlo_single.m` 定义四类工况，通过 `RUN_CASE` + `SUB_IDX` 选择：

| RUN_CASE | 名称 | 子工况 |
|---------|------|------|
| **T** | 目标机动 | T1:匀速直飞, T2:低频小幅, T3:中频中等, T4:高频大幅 |
| **G** | 交战几何 | G1:标称, G2:近距小偏, G3:近距大偏, G4:远距小偏, G5:远距大偏 |
| **AP** | 驾驶仪退化 | AP1:全标称, AP2:时间常数退化, AP3:轻度, AP4:中度, AP5:重度 |
| **R** | 综合鲁棒 | R1:全标称, R2:多参数摄动, R3:大姿态偏差 |
| **ALL** | 全工况 | 依次运行 T/G/AP/R |

---

## Layer 2 工具清单

> RL 优化完全由 **Layer 3 OptimizationWorkflow** 执行，不在 Hermes 工具集内。

| 工具名 | 所属子智能体 | 功能 |
|--------|------------|------|
| `rag_query` | rag_agent | Agentic 多跳检索（自动分解子查询） |
| `rag_retrieve` | rag_agent | 单次向量检索知识库 |
| `rag_expand` | rag_agent | 按 ID 获取文档全文 |
| `generate_matlab` | matlab_agent | 生成 .m 脚本（monte_carlo_single 模板） |
| `syntax_check_matlab` | matlab_agent / sim_agent | 验证并修复 .m 文件 |
| `verify_guidance_compat` | matlab_agent | 数学适配性证明（带宽分离/Adjoint/PM） |
| `run_simulation` | sim_agent | 运行 monte_carlo_single，输出命中率/SEP/PeakNy/PM/BW |
| `judge_requirements` | analysis_agent | 判断仿真指标是否满足任务要求 |
| `parameter_experience_best` | analysis_agent | 获取历史最优参数 |
| `parameter_experience_search` | analysis_agent | 搜索相似历史参数 |
| `agent_memory_remember` | memory_agent | 持久化写入长期记忆（JSON KV） |
| `agent_memory_recall` | memory_agent | 读取长期记忆条目 |
| `agent_memory_list` | memory_agent | 列出所有记忆键 |
| `agent_memory_forget` | memory_agent | 删除记忆条目 |
| `call_specialist` | Hermes 编排器 | 委托子智能体执行（含 agent_type 路由） |

---

## 子智能体间数据传递

子智能体通过 **`context` 参数**传递上一步的结构化 JSON 输出：

```
Hermes 编排器
│
├─ RAG_RESULT  = call_specialist(agent_type='rag_agent', task='检索APN制导律知识')
│                → 返回 JSON: {law_type, key_params, design_principles, sources}
│
├─ MATLAB_RESULT = call_specialist(agent_type='matlab_agent',
│                    task='生成脚本 mission_conditions="G:3"',
│                    context=RAG_RESULT)          ← RAG结果作为背景
│                  → 返回 JSON: {script_path, compat_overall, compat_score, key_params}
│
├─ SIM_RESULT  = call_specialist(agent_type='sim_agent',
│                    task='运行仿真 script_path=<MATLAB_RESULT中的script_path>')
│                → 返回 JSON: {status, hit_rate, SEP, PeakNy, PM, BW}
│
└─ JUDGE_RESULT = call_specialist(agent_type='analysis_agent',
                     task='判断是否满足需求',
                     context=SIM_RESULT)          ← 仿真指标作为背景
                   → 返回 JSON: {satisfied, layer3_path, metrics_vs_req}
```

每个子智能体强制在响应末尾输出 ` ```json ... ``` ` 块，Hermes 从中提取 `script_path`、`satisfied` 等字段。

---

## PPO 强化学习参数优化

`MatlabRLOptimizer` 对 **monte_carlo_single.m 的 `RL_PARAMS` 块**进行 **9 维** PPO 优化（8 驾驶仪 + N_pn）。

**奖励函数**（`config.yaml` 中 `reward_weights` 可调）：
```
reward = w_hit × hit_rate
       + sep_bonus(SEP)
       + pm_bonus(PM)          # 在目标范围 [pm_min, pm_max] 内加分
       + bw_bonus(BW)
       - peak_ny_penalty(PeakNy)
```

**反思智能体作为早停决策者**：

| 触发 | 退出状态 | 说明 |
|-----|---------|------|
| `ReflectionAgent` 返回 `needs_optimization=False` | `task_requirements_met` | 所有要求满足，立即停止 |
| 跑满 `max_episodes` | `success` | 自然结束，输出最优 |

**典型日志**：
```
[Ep 3/20] reward=2.821  hit=85.0%  SEP=2.94m  PM=38.2°  BW=22.1r/s
[RL Reflection @ Ep 3] needs_optimization=False → 已满足全部要求
✓ RL early-stopped (episode 3): task_requirements_met
```

---

## 消融实验设计

五个消融维度，七组实验配置（通过修改 `config.yaml` 的 `ablation` 块 + `workflow.max_iterations` 切换）：

| 组别 | 适配验证 | 语法检查 | RL优化 | 经验库 | max_iterations | 验证目标 |
|------|:-------:|:-------:|:------:|:------:|:--------------:|---------|
| **完整系统** | ✅ | ✅ | ✅ | ✅ | 5 | 基准（最优） |
| **A 去适配验证** | ❌ | ✅ | ✅ | ✅ | 5 | 制导律数学适配性证明的贡献 |
| **B 去语法检查** | ✅ | ❌ | ✅ | ✅ | 5 | LLM 迭代语法修正的贡献 |
| **C 去RL优化** | ✅ | ✅ | ❌ | ✅ | 5 | PPO 参数调优的贡献 |
| **D 去经验库** | ✅ | ✅ | ✅ | ❌ | 5 | 历史参数跨任务复用的贡献 |
| **E 单轮迭代** | ✅ | ✅ | ✅ | ✅ | 1 | 多轮「生成-优化-反思」的贡献 |
| **F 纯对照** | ❌ | ❌ | ❌ | ❌ | 1 | LLM 直接输出基线 |

**切换方式**（以组 C 去RL为例）：

```yaml
# config.yaml
ablation:
  guidance_compat_verification: { enabled: true  }
  syntax_check:                 { enabled: true  }
  rl_optimization:              { enabled: false }
  parameter_experience_reuse:   { enabled: true  }
  reflection_agent:             { enabled: true  }
workflow:
  max_iterations: 5
```

**推荐评估指标**：在相同工况（如 G3, AP3, R2）下各跑 N 次，统计：

| 指标 | 说明 |
|------|------|
| 命中率均值/方差 | 精度 |
| SEP 均值/方差 | 脱靶量 |
| 收敛 episode 数 | 优化效率（仅完整/A/B/D/E 组有效） |
| Layer2 脚本一次通过率 | 语法检查修正的效果（对比 B 组） |
| 制导律适配验证通过率 | 数学证明的筛选能力（对比 A 组） |
| 总 API 调用次数 | 推理成本 |

---

## 配置文件关键字段

```yaml
llm:
  provider: custom             # openai | anthropic | openrouter | custom
  base_url: https://api.deepseek.com
  model:    deepseek-v4-pro
  api_key:  <your key>

rag:
  embedding_provider: custom
  embedding_model:    text-embedding-v3
  embedding_dim:      1024

workflow:
  max_iterations:    5         # 外层 Layer2→Layer3 迭代上限
  hermes_execution:  true
  hermes_tool_timeout: 0       # 0=不限时

matlab_rl_optimizer:
  max_episodes:  20            # PPO 最大回合数
  nmc_per_eval:  10            # 每回合蒙特卡洛次数

simulation:
  engine: matlab_engine        # auto | matlab_engine | matlab | octave | python
```

---

## 已知问题

- **Octave/MATLAB 未安装**：RL 自动回退 Python 仿真，不阻塞训练
- **LLM 返回空响应**：TaskPlanner 默认返回 `REUSE_HISTORY`（最安全路径）
- **`agent_memory_*` 报 "Memory not initialized"**：根因是 `HermesAgentMemory.__len__==0` 被当作 falsy，已修复为 `is not None` 判断
- **`roots: NaN`**：RL 极端参数导致驾驶仪设计矩阵 Inf/NaN，模板已加 `safe_coef()` + `try/catch` 防护

---

## 替换仿真模板

替换 `monte_carlo_single.m` 时需同步修改的文件：

| # | 文件 | 检查点 |
|---|------|--------|
| 1 | 新 `.m` 模板 | `RL_PARAMS_BEGIN/END` 块存在，`rl_*` 变量完整 |
| 2 | 新 `.m` 模板 | stdout 含命中率/SEP/PeakNy/PM/BW 字样 |
| 3 | `matlab_rl_optimizer.py` | `AUTOPILOT_PARAM_SPECS`、`RL_PARAM_TO_MATLAB` 与模板一致 |
| 4 | `matlab_rl_optimizer.py` | `CATEGORY_DEFS` 工况编号与模板 SC{} 数组一致 |
| 5 | `conditions.md` | 子工况编号与物理含义同步 |
| 6 | `simulation_tool.py` | KB 模板默认路径指向新文件 |
| 7 | `config.yaml` | 奖励权重和指标阈值匹配新模板量纲 |

---

## License

MIT
