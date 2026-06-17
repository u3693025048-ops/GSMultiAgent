# 优化流程完整分析

## 🏗️ 系统架构（3层）

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: CLI Agent (cli_agent.py)                              │
│ - 自然语言输入解析                                              │
│ - 工况条件提取 (T/G/AP/R)                                       │
│ - 主循环控制 (最多max_iterations次迭代)                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2: Hermes Agent (hermes_integration.py)                  │
│ 6个工具：                                                       │
│ 1. rag_retrieve - 知识库检索                                   │
│ 2. generate_matlab - 生成制导律代码                            │
│ 3. generate_sysml - 生成系统模型                               │
│ 4. syntax_check_matlab - 语法检查                              │
│ 5. run_simulation - 运行仿真                                   │
│ 6. judge_requirements - 判定需求是否满足                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: OptimizationWorkflow (optimization_workflow.py)       │
│ - RL优化器 (MatlabRLOptimizer)                                 │
│ - 判定智能体 (JudgmentAgent)                                   │
│ - 反思智能体 (ReflectionAgent)                                 │
│ - 参数经验库 (ParameterExperience)                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 单次迭代流程

### 迭代 N

```
┌─────────────────────────────────────────────────────────────────┐
│ [Step 1] 初始化组件                                             │
│ - RAG知识库                                                     │
│ - Hermes Agent                                                  │
│ - RL优化器                                                      │
│ - 反思智能体                                                    │
│ - 参数经验库                                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 2] 任务规划与参数提取                                     │
│                                                                 │
│ 2.1 IntelligentTaskPlanner 分析                               │
│     - 分析用户提示词                                            │
│     - 融合反思反馈 (prev_suggestion)                           │
│     - 分析脚本结构 (monte_carlo_single.m)                      │
│     - 选择设计路径 (TUNE_PARAMS / MODIFY_LAW / HYBRID)        │
│                                                                 │
│ 2.2 工况分析与映射                                              │
│     - 从提示词提取工况条件 (T/G/AP/R)                         │
│     - LLM验证工况映射                                           │
│                                                                 │
│ 2.3 参数提取                                                    │
│     - 从最新MATLAB脚本提取参数                                 │
│     - 或使用参数经验库中的最优参数                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 2.5] Hermes生成制导律代码                                │
│                                                                 │
│ 2.5.1 Hermes运行工具链                                        │
│       - rag_retrieve: 检索相关知识                              │
│       - generate_matlab: 生成制导律代码                        │
│       - syntax_check_matlab: 检查语法                          │
│       - run_simulation: 运行仿真验证                           │
│       - judge_requirements: 判定是否满足要求                  │
│                                                                 │
│ 2.5.2 结果判定                                                 │
│       - satisfied=True → 跳过RL，直接进入反思                 │
│       - satisfied=False → 进入RL优化                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 3] RL优化 (MatlabRLOptimizer.optimize)                   │
│                                                                 │
│ 3.1 初始化                                                      │
│     - 加载参数经验库中的最优参数作为warm-start                 │
│     - 初始化PPO网络 (Actor/Critic)                            │
│     - 初始化FRE v2 (可行域探索)                               │
│                                                                 │
│ 3.2 主优化循环 (最多max_episodes次)                           │
│     for ep in range(max_episodes):                             │
│       a) 采样action (PPO策略)                                 │
│       b) 执行action → 新参数                                   │
│       c) 运行仿真 → 获得metrics                               │
│       d) 计算奖励 (多目标加权)                                │
│       e) FRE v2处理:                                          │
│          - 检查异常值                                          │
│          - 修改奖励 (多目标约束加成)                          │
│          - 更新阶段状态                                        │
│          - 判定进阶/回滚                                       │
│       f) 反思智能体检查 (每reflect_every个episode)           │
│          - 调用ReflectionAgent.reflect()                      │
│          - 判定是否满足任务要求                                │
│          - 满足 → 早期退出，保存参数                          │
│       g) PPO更新 (每episodes_per_update个episode)            │
│       h) 保存到参数经验库                                      │
│                                                                 │
│ 3.3 优化结束                                                    │
│     - status: 'success' (达到max_episodes)                    │
│     - status: 'task_requirements_met' (反思判定满足)          │
│     - 返回最优参数和指标                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 3.5] 快速路径检查                                        │
│                                                                 │
│ - 检查RL结果是否满足任务要求                                   │
│ - 满足 → 跳过反思，直接进入报告生成                            │
│ - 不满足 → 进入反思智能体                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 4] 反思与迭代决策 (ReflectionAgent)                      │
│                                                                 │
│ 4.1 调用反思智能体                                              │
│     - 分析当前最优参数和指标                                    │
│     - 评估是否满足所有要求                                      │
│     - 提出改进建议                                              │
│                                                                 │
│ 4.2 反思结果                                                    │
│     - needs_optimization=False                                 │
│       → 任务完成，进入报告生成                                 │
│     - needs_optimization=True                                  │
│       → 需要继续优化，生成新提示词                             │
│       → 进入下一迭代                                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ [Step 5] 参数持久化与报告生成                                   │
│                                                                 │
│ 5.1 保存最优参数                                                │
│     - 保存到参数经验库 (parameter_experience)                  │
│     - 保存到guidance_output/                                   │
│                                                                 │
│ 5.2 生成优化报告                                                │
│     - 汇总所有迭代的结果                                        │
│     - 记录最优参数和指标                                        │
│     - 输出到guidance_output/report_*.md                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔄 多迭代循环

```
迭代 1:
  ├─ Step 2: 任务规划 → 选择 TUNE_PARAMS
  ├─ Step 2.5: Hermes生成初始制导律
  ├─ Step 3: RL优化 → 得到最优参数 P1
  ├─ Step 4: 反思 → "需要改进PM和BW"
  └─ 生成新提示词 → 迭代 2

迭代 2:
  ├─ Step 2: 任务规划 → 选择 MODIFY_LAW
  ├─ Step 2.5: Hermes根据反思建议修改制导律
  ├─ Step 3: RL优化 → 得到最优参数 P2
  ├─ Step 4: 反思 → "需要降低PeakNy"
  └─ 生成新提示词 → 迭代 3

迭代 3:
  ├─ Step 2: 任务规划 → 选择 HYBRID
  ├─ Step 2.5: Hermes混合优化
  ├─ Step 3: RL优化 → 得到最优参数 P3
  ├─ Step 4: 反思 → "所有要求都满足！"
  └─ 进入报告生成 → 完成
```

---

## 🎯 关键决策点

### 1. 设计路径选择 (Step 2)

```
用户提示词
    ↓
IntelligentTaskPlanner 分析
    ↓
选择设计路径：
├─ TUNE_PARAMS: 仅调整自动驾驶仪参数
├─ MODIFY_LAW: 修改制导律
└─ HYBRID: 同时修改制导律和参数
```

### 2. 快速路径判定 (Step 2.5)

```
Hermes生成制导律
    ↓
judge_requirements 检查
    ↓
满足要求？
├─ YES → 跳过RL，直接反思
└─ NO → 进入RL优化
```

### 3. RL早期退出 (Step 3)

```
每个episode：
    ↓
反思智能体检查 (每reflect_every个episode)
    ↓
满足任务要求？
├─ YES → 早期退出，保存参数
└─ NO → 继续优化
```

### 4. 迭代继续判定 (Step 4)

```
反思智能体评估
    ↓
needs_optimization？
├─ NO → 任务完成，生成报告
└─ YES → 生成改进建议，进入下一迭代
```

---

## 📈 FRE v2 在RL中的作用

```
RL优化循环中：

每个episode:
  ├─ 计算基础奖励
  ├─ FRE v2处理:
  │  ├─ 检查异常值 (超过硬约束的2倍)
  │  ├─ 修改奖励 (多目标约束加成)
  │  ├─ 更新阶段状态
  │  └─ 判定进阶/回滚
  └─ PPO更新

FRE v2的4个阶段：
  Phase 0: 宽松约束 (快速找到初步可行解)
  Phase 1: 中等约束 (逐步改进)
  Phase 2: 严格约束 (精细调优)
  Phase 3: 最终约束 (最终验证)

阶段进阶条件：
  - 连续5个episodes满足约束 → 立即进入下一阶段
  - 或达到最大轮次(30) → 进入下一阶段

阶段回滚条件：
  - 连续10个episodes失败 → 回滚到上一阶段
  - 任何指标超过硬约束的2倍 → 回滚
  - 达到最大轮次但未充分成功 → 回滚
```

---

## 💾 参数经验库 (ParameterExperience)

```
参数经验库的作用：

1. Warm-start:
   - 启动时从PE加载最优参数
   - 作为RL的初始条件

2. 每个episode保存:
   - 参数值
   - 仿真指标
   - 奖励值
   - 任务上下文

3. 跨迭代复用:
   - 下一迭代可以检索历史最优参数
   - 加速优化收敛

4. 长期学习:
   - 跨多个优化任务保留经验
   - 支持参数重用和迁移学习
```

---

## 🔍 反思智能体 (ReflectionAgent)

```
反思智能体的作用：

1. 每个episode判定 (当有新的best时):
   - 调用LLM评估当前最优参数
   - 判定是否满足任务要求
   - 返回 needs_optimization (True/False)

2. 迭代末期判定:
   - 综合分析所有指标
   - 提出改进建议
   - 生成新的优化提示词

3. 最终判定:
   - 确认所有要求都满足
   - 触发报告生成和任务完成
```

---

## 📊 关键配置参数

### RL优化器配置

```yaml
matlab_rl_optimizer:
  max_episodes: 50              # 最多50个episodes
  episodes_per_update: 64       # 每64个episode更新一次PPO
  nmc_per_eval: 10              # 每个episode运行10次蒙特卡洛仿真
  
  early_stop:
    enabled: true               # 启用早期退出
    reflect_every: 1            # 每个episode检查一次反思
    min_episodes: 5             # 最少5个episodes后才能早期退出
    patience: 10                # 10个episode无改进则停止
```

### FRE v2配置

```yaml
fre:
  enabled: true                 # 启用FRE v2
  early_stop_window: 5          # 连续5个episodes提前终止
  failure_threshold: 10         # 连续10个episodes失败回滚
  max_phase_episodes: 30        # 每个阶段最多30个episodes
```

### 工作流配置

```yaml
workflow:
  max_iterations: 10            # 最多10次迭代
```

---

## 🎓 完整示例流程

```
用户输入: "T4工况，要求命中率>=92%，SEP<=7m，PeakNy<=20g"

迭代 1:
  Step 2: 分析 → TUNE_PARAMS (仅调参)
  Step 2.5: Hermes生成初始制导律
  Step 3: RL优化 50个episodes
    - Phase 0 (宽松): 5个episodes → 找到初步可行解
    - Phase 1 (中等): 8个episodes → 改进质量
    - Phase 2 (严格): 12个episodes → 精细调优
    - Phase 3 (最终): 25个episodes → 最终验证
  Step 4: 反思 → "命中率达标，但SEP=8.5m，需要改进"

迭代 2:
  Step 2: 分析 → MODIFY_LAW (修改制导律)
  Step 2.5: Hermes修改制导律以降低SEP
  Step 3: RL优化 50个episodes
    - 类似的阶段进阶
  Step 4: 反思 → "SEP达标，但PeakNy=22g，需要降低"

迭代 3:
  Step 2: 分析 → HYBRID (混合优化)
  Step 2.5: Hermes混合优化
  Step 3: RL优化 30个episodes (早期退出)
    - 反思判定所有要求都满足
    - 早期退出，保存参数
  Step 4: 反思 → "所有要求都满足！"

Step 5: 生成报告
  - 最优参数: w1=46.25, zeta1=0.35, ...
  - 最优指标: 命中率=100%, SEP=4.66m, PeakNy=17.23g
  - 优化过程: 3次迭代，共130个episodes
```

---

## 总结

**当前优化流程是一个多层级、多智能体的迭代系统**：

1. **Layer 1 (CLI)**: 自然语言输入 → 工况解析
2. **Layer 2 (Hermes)**: 制导律生成 → 快速验证
3. **Layer 3 (Workflow)**: RL优化 → 反思迭代

**关键特性**：
- ✅ 多次迭代，逐步改进
- ✅ 智能设计路径选择
- ✅ FRE v2多阶段探索
- ✅ 反思智能体早期退出
- ✅ 参数经验库跨迭代复用
- ✅ 异常检测与自动回滚

**预期结果**：
- 3-5次迭代完成优化
- 每次迭代30-50个episodes
- 总耗时 15-30 分钟
- 最终满足所有用户要求
