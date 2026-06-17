# 优化流程快速参考

## 🏗️ 系统3层架构

```
Layer 1: CLI Agent (cli_agent.py)
  ↓ 自然语言输入
Layer 2: Hermes Agent (6个工具)
  ↓ 制导律生成 + 快速验证
Layer 3: OptimizationWorkflow
  ├─ RL优化器 (MatlabRLOptimizer)
  ├─ 判定智能体 (JudgmentAgent)
  ├─ 反思智能体 (ReflectionAgent)
  └─ 参数经验库 (ParameterExperience)
```

---

## 📊 单次迭代流程（5步）

### Step 1: 初始化
- RAG知识库
- Hermes Agent
- RL优化器
- 反思智能体
- 参数经验库

### Step 2: 任务规划
- 分析用户提示词
- 融合前一次反思反馈
- 选择设计路径：
  - **TUNE_PARAMS**: 仅调参
  - **MODIFY_LAW**: 修改制导律
  - **HYBRID**: 混合优化

### Step 2.5: Hermes生成制导律
```
Hermes运行工具链：
  1. rag_retrieve → 检索知识
  2. generate_matlab → 生成代码
  3. syntax_check_matlab → 检查语法
  4. run_simulation → 仿真验证
  5. judge_requirements → 判定是否满足

结果：
  ├─ satisfied=True → 跳过RL，直接反思
  └─ satisfied=False → 进入RL优化
```

### Step 3: RL优化
```
MatlabRLOptimizer.optimize():
  
  初始化：
    - 加载参数经验库的最优参数 (warm-start)
    - 初始化PPO网络
    - 初始化FRE v2

  主循环 (最多max_episodes):
    for ep in range(max_episodes):
      a) 采样action (PPO)
      b) 执行 → 新参数
      c) 仿真 → metrics
      d) 计算奖励
      e) FRE v2处理：
         - 检查异常值
         - 修改奖励
         - 更新阶段
         - 判定进阶/回滚
      f) 反思检查 (每reflect_every个episode)
         - 满足要求？→ 早期退出
      g) PPO更新
      h) 保存到参数经验库

  结束：
    - status='success' (达到max_episodes)
    - status='task_requirements_met' (反思判定)
```

### Step 3.5: 快速路径检查
- 检查RL结果是否满足要求
- 满足 → 跳过反思，生成报告
- 不满足 → 进入反思智能体

### Step 4: 反思与迭代决策
```
ReflectionAgent:
  - 分析最优参数和指标
  - 评估是否满足所有要求
  - 提出改进建议

结果：
  ├─ needs_optimization=False → 任务完成
  └─ needs_optimization=True → 生成新提示词，进入下一迭代
```

### Step 5: 报告生成
- 保存最优参数到参数经验库
- 生成优化报告 (guidance_output/report_*.md)

---

## 🔄 多迭代循环

```
迭代 1 → TUNE_PARAMS → RL优化 → 反思 → "需要改进PM"
迭代 2 → MODIFY_LAW → RL优化 → 反思 → "需要降低PeakNy"
迭代 3 → HYBRID → RL优化 → 反思 → "所有要求满足！"
完成 → 生成报告
```

---

## 🎯 FRE v2 在RL中的作用

```
RL优化循环中的FRE v2：

每个episode:
  ├─ 计算基础奖励
  ├─ FRE v2处理:
  │  ├─ 检查异常值 (超过硬约束的2倍)
  │  ├─ 修改奖励 (多目标约束加成)
  │  ├─ 更新阶段状态
  │  └─ 判定进阶/回滚
  └─ PPO更新

4个阶段：
  Phase 0: 宽松约束 (快速找初步解)
  Phase 1: 中等约束 (逐步改进)
  Phase 2: 严格约束 (精细调优)
  Phase 3: 最终约束 (最终验证)

进阶条件：
  ✓ 连续5个episodes满足约束 → 立即进入下一阶段
  ✓ 或达到最大轮次(30) → 进入下一阶段

回滚条件：
  ✓ 连续10个episodes失败 → 回滚
  ✓ 任何指标超过硬约束的2倍 → 回滚
  ✓ 达到最大轮次但未充分成功 → 回滚
```

---

## 💾 参数经验库

```
ParameterExperience的作用：

1. Warm-start:
   - 启动时加载最优参数
   - 作为RL初始条件

2. 每个episode保存:
   - 参数值
   - 仿真指标
   - 奖励值

3. 跨迭代复用:
   - 下一迭代检索历史最优参数
   - 加速收敛

4. 长期学习:
   - 跨多个优化任务保留经验
   - 支持参数迁移
```

---

## 🔍 反思智能体

```
ReflectionAgent的作用：

1. 每个episode判定:
   - 当有新best时调用
   - 评估是否满足要求
   - 返回 needs_optimization

2. 迭代末期判定:
   - 综合分析所有指标
   - 提出改进建议
   - 生成新提示词

3. 最终判定:
   - 确认所有要求满足
   - 触发报告生成
```

---

## 📈 关键配置

```yaml
# RL优化器
matlab_rl_optimizer:
  max_episodes: 50              # 最多50个episodes
  early_stop.reflect_every: 1   # 每个episode检查反思
  
# FRE v2
fre:
  early_stop_window: 5          # 连续5个episodes提前终止
  failure_threshold: 10         # 连续10个episodes失败回滚
  max_phase_episodes: 30        # 每个阶段最多30个episodes

# 工作流
workflow:
  max_iterations: 10            # 最多10次迭代
```

---

## 📊 完整示例

```
用户输入: "T4工况，命中率>=92%，SEP<=7m，PeakNy<=20g"

迭代 1: TUNE_PARAMS
  ├─ Hermes生成初始制导律
  ├─ RL优化 50个episodes (FRE v2: 4个阶段)
  └─ 反思: "SEP=8.5m，需要改进"

迭代 2: MODIFY_LAW
  ├─ Hermes修改制导律
  ├─ RL优化 50个episodes
  └─ 反思: "PeakNy=22g，需要降低"

迭代 3: HYBRID
  ├─ Hermes混合优化
  ├─ RL优化 30个episodes (早期退出)
  └─ 反思: "所有要求满足！"

完成: 生成报告
  - 最优参数: w1=46.25, zeta1=0.35, ...
  - 最优指标: 命中率=100%, SEP=4.66m, PeakNy=17.23g
  - 总耗时: 3次迭代，130个episodes
```

---

## 🎓 关键决策点

| 决策点 | 位置 | 条件 | 结果 |
|--------|------|------|------|
| **设计路径** | Step 2 | 任务分析 | TUNE / MODIFY / HYBRID |
| **快速路径** | Step 2.5 | judge_requirements | 跳过RL / 进入RL |
| **早期退出** | Step 3 | 反思判定 | 继续RL / 早期退出 |
| **迭代继续** | Step 4 | 反思评估 | 完成 / 下一迭代 |

---

## 📝 详细说明

见 `OPTIMIZATION_WORKFLOW_ANALYSIS.md`
