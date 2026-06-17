# Feasible Region Explorer (FRE) 使用指南

## 问题背景

T4工况的可行域非常狭窄，容易跳变，导致RL优化难以探索到符合要求的解。

**症状**：
- 奖励在约束边界处跳变
- 难以找到可行解
- 探索效率低下

---

## 解决方案：逐步探索可行域

### 核心思想

**从宽松约束逐步紧化到严格约束**

```
Phase 0: 宽松约束
├─ SEP <= 100m
├─ HitRate >= 50%
└─ 20 episodes

Phase 1: 中等约束
├─ SEP <= 53.5m
├─ HitRate >= 71%
└─ 20 episodes

Phase 2: 严格约束
├─ SEP <= 7m
├─ HitRate >= 92%
└─ 20 episodes
```

### 工作流程

1. **Phase 0（宽松）**：用宽松的约束快速找到初步可行解
2. **Phase 1（中等）**：逐步紧化约束，改进解质量
3. **Phase 2（严格）**：在严格约束下精细调优

### 自动进阶条件

每个阶段自动进阶到下一阶段，当满足：
- ✅ 已运行 20 个 episodes
- ✅ 找到至少 1 个可行解

---

## 实现细节

### 1. FeasibleRegionExplorer 类

**初始化**：
```python
fre = FeasibleRegionExplorer(
    initial_sep_threshold=100.0,      # 初始SEP约束（宽松）
    initial_hit_rate_threshold=50.0,  # 初始命中率约束（宽松）
    target_sep_threshold=7.0,         # 目标SEP约束（严格）
    target_hit_rate_threshold=92.0,   # 目标命中率约束（严格）
    phase_episodes=20,                # 每个阶段的episode数
    num_phases=3,                     # 3个阶段
)
```

**核心方法**：

| 方法 | 功能 |
|------|------|
| `get_current_thresholds()` | 获取当前阶段的约束阈值 |
| `is_feasible(metrics)` | 检查是否满足当前阶段的可行性约束 |
| `update_episode(metrics, reward)` | 更新episode计数和统计 |
| `should_advance_phase()` | 判断是否应该进入下一阶段 |
| `advance_phase()` | 进入下一阶段 |
| `get_exploration_bonus(metrics)` | 获取探索奖励加成 |
| `log_phase_status()` | 记录当前阶段状态 |

### 2. FeasibleRegionRewardModifier 类

**作用**：修改奖励函数，加入可行域探索的奖励加成

```python
modifier = FeasibleRegionRewardModifier(fre)
modified_reward = modifier.modify_reward(base_reward, metrics)
```

**奖励加成逻辑**：
- 在当前阶段的可行域内，给予额外奖励
- 离约束边界越远，奖励越大
- 鼓励在可行域内探索

---

## 日志输出示例

### 初始化日志
```
[FRE] Initialized with 3 phases | SEP: 100.0m → 7.0m | HitRate: 50.0% → 92.0%
[FRE] SEP thresholds: ['100.0', '53.5', '7.0']
[FRE] HitRate thresholds: ['50.0', '71.0', '92.0']
```

### 运行中日志
```
[FRE] Phase 0/2 | Episodes: 5/20 | Feasible: 2 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 10/20 | Feasible: 5 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 15/20 | Feasible: 8 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 20/20 | Feasible: 12 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0 completed (20 episodes, 12 feasible). Advancing to phase 1...
[FRE] Phase 1 constraints: SEP <= 53.5m, HitRate >= 71.0%
```

### 完成日志
```
[FRE] Phase 2 completed (20 episodes, 15 feasible). Advancing to phase 3...
[FRE] All phases completed!
```

---

## 预期效果

### 优化过程

```
Episode 1-20 (Phase 0 - 宽松):
  ├─ 快速找到初步可行解
  ├─ SEP 从 200m → 80m
  └─ HitRate 从 30% → 60%

Episode 21-40 (Phase 1 - 中等):
  ├─ 逐步改进解质量
  ├─ SEP 从 80m → 20m
  └─ HitRate 从 60% → 85%

Episode 41-60 (Phase 2 - 严格):
  ├─ 精细调优
  ├─ SEP 从 20m → 7m
  └─ HitRate 从 85% → 92%
```

### 性能指标

| 指标 | 标准PPO | FRE | 改进 |
|------|---------|-----|------|
| 找到可行解的episode | 30-40 | 15-20 | **-50%** |
| 总episode数 | 50-100 | 40-60 | **-30%** |
| 最终SEP | 8-10m | 6-7m | **-20%** |
| 最终HitRate | 90% | 93% | **+3%** |

---

## 配置调优

### 调整约束范围

如果要改变约束范围，修改`__init__`中的参数：

```python
self._fre = FeasibleRegionExplorer(
    initial_sep_threshold=150.0,      # 更宽松的初始约束
    initial_hit_rate_threshold=40.0,  # 更宽松的初始约束
    target_sep_threshold=5.0,         # 更严格的目标约束
    target_hit_rate_threshold=95.0,   # 更严格的目标约束
    phase_episodes=25,                # 每个阶段更多episodes
    num_phases=4,                     # 4个阶段而不是3个
)
```

### 调整阶段数

- **更多阶段（4-5个）**：更平缓的约束过渡，但总episode数增加
- **更少阶段（2个）**：更快的约束过渡，但可能跳过可行解

### 调整每个阶段的episode数

- **更多episodes（30-40）**：在每个阶段充分探索
- **更少episodes（10-15）**：快速进入下一阶段

---

## 与其他方案的对比

### vs 梯度陡峭检测（Solution 1）

| 特性 | 梯度检测 | FRE |
|------|---------|-----|
| **原理** | 检测梯度陡峭，降低探索 | 逐步紧化约束 |
| **适用场景** | 已在可行域附近 | 难以找到可行域 |
| **优点** | 简单，计算快 | 系统性，效果好 |
| **缺点** | 需要先找到可行域 | 需要更多episodes |

**建议**：两者结合使用
- FRE 用于逐步探索可行域
- 梯度检测 用于在可行域内精细调优

---

## 故障排查

### 问题1：无法进入下一阶段

**症状**：
```
[FRE] Phase 0/2 | Episodes: 20/20 | Feasible: 0
```

**原因**：在当前阶段未找到可行解

**解决**：
1. 增加初始约束的宽松度
2. 增加每个阶段的episode数
3. 检查奖励函数是否正确

### 问题2：奖励加成过大

**症状**：
```
reward_with_fre_bonus = 5.0 (太大)
```

**原因**：探索奖励加成计算不当

**解决**：调整 `get_exploration_bonus()` 中的系数

### 问题3：约束过渡太快

**症状**：
```
Phase 0 → Phase 1 → Phase 2 (太快，未充分探索)
```

**原因**：`phase_episodes` 设置太小

**解决**：增加 `phase_episodes` 到 30-40

---

## 完整示例

```python
# 初始化
fre = FeasibleRegionExplorer(
    initial_sep_threshold=100.0,
    initial_hit_rate_threshold=50.0,
    target_sep_threshold=7.0,
    target_hit_rate_threshold=92.0,
    phase_episodes=20,
    num_phases=3,
)
modifier = FeasibleRegionRewardModifier(fre)

# 在优化循环中
for ep in range(max_episodes):
    # ... 运行仿真，获得metrics ...
    
    # 计算基础奖励
    reward = compute_reward(metrics)
    
    # 应用FRE奖励修改
    reward_with_bonus = modifier.modify_reward(reward, metrics)
    
    # 更新FRE状态
    fre.update_episode(metrics, reward)
    
    # 定期记录状态
    if (ep + 1) % 5 == 0:
        fre.log_phase_status()
    
    # 检查是否进入下一阶段
    if fre.should_advance_phase():
        fre.advance_phase()
    
    # 使用修改后的奖励进行PPO更新
    update_ppo(reward_with_bonus)
```

---

## 相关文档

- `STEEP_GRADIENT_FIX.md` - 梯度陡峭检测方案
- `matlab_rl_optimizer.py` - RL优化器实现
- `feasible_region_explorer.py` - FRE核心实现

---

## 总结

**FRE（Feasible Region Explorer）** 通过逐步紧化约束，系统地探索可行域，解决T4工况可行域狭窄的问题。

**关键特性**：
✅ 自动约束过渡  
✅ 可行域内奖励加成  
✅ 详细的进度日志  
✅ 灵活的参数调优  

**预期结果**：
✅ 找到可行解的速度提升 50%  
✅ 最终解质量提升 20%  
✅ 优化过程更加稳定  
