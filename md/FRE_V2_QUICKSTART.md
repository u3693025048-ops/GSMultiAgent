# FRE v2 快速开始

## 四大核心改进

### 1️⃣ 多目标约束管理
```python
PhaseConstraints(
    sep_max=100.0,           # SEP硬约束
    hit_rate_min=50.0,       # 命中率硬约束
    peak_ny_max=25.0,        # PeakNy硬约束
    pm_min=30.0, pm_max=70.0,  # PM硬约束范围
    bw_min=10.0, bw_max=85.0,  # BW硬约束范围
)
```

**效果**：避免RL为了追求SEP和命中率而无限制提高带宽和导引比

---

### 2️⃣ 异常处理与回滚
```python
# 异常检测：超过硬约束的2倍
# 例如：PeakNy硬约束=20g → 异常阈值=40g

# 自动回滚条件：
# ✓ 连续10个episodes失败
# ✓ 任何指标超出硬约束的2倍
# ✓ 达到最大轮次(30)但未充分成功
```

**效果**：自动处理BW=162、PeakNy=61g这种极端异常值

---

### 3️⃣ 自适应超参数
```python
# 根据阶段进度动态衰减
decay_factor = 1.0 - progress * 0.5

# 例如：
# progress=0.0: lr_actor = 1e-4 (100%)
# progress=0.5: lr_actor = 7.5e-5 (75%)
# progress=1.0: lr_actor = 5e-5 (50%)
```

**效果**：前期充分探索，后期逐步收敛，避免震荡

---

### 4️⃣ 智能阶段管理

**提前终止**：连续5个episodes都满足约束 → 立即进入下一阶段

**失败回滚**：连续10个episodes失败 → 回滚到上一阶段

**最大轮次保护**：每个阶段最多30个episodes

---

## 初始化

```python
from multi_agent.rl.feasible_region_explorer_v2 import (
    FeasibleRegionExplorerV2,
    PhaseConstraints,
    FeasibleRegionRewardModifierV2,
)

# 定义约束
phase_constraints = [
    PhaseConstraints(phase_id=0, sep_max=100.0, hit_rate_min=50.0, ...),
    PhaseConstraints(phase_id=1, sep_max=50.0, hit_rate_min=75.0, ...),
    PhaseConstraints(phase_id=2, sep_max=7.0, hit_rate_min=92.0, ...),
]

# 初始化
fre = FeasibleRegionExplorerV2(
    phase_constraints=phase_constraints,
    early_stop_window=5,
    failure_threshold=10,
    max_phase_episodes=30,
)

modifier = FeasibleRegionRewardModifierV2(fre)
```

---

## 在优化循环中使用

```python
for ep in range(max_episodes):
    # 运行仿真
    reward = compute_reward(metrics)
    
    # 应用FRE v2
    reward_with_bonus = modifier.modify_reward(reward, metrics)
    
    # 更新阶段状态
    decision = fre.update_episode(metrics, reward, new_params)
    
    # 处理决策
    if decision['action'] == 'advance':
        logger.info(f"进入下一阶段：{decision['reason']}")
    elif decision['action'] == 'rollback':
        logger.warning(f"回滚：{decision['reason']}")
        restore_params(fre.phase_best_params)
    
    if decision['should_stop']:
        break
    
    # PPO更新
    update_ppo(reward_with_bonus)
```

---

## 预期效果

| 指标 | FRE v1 | FRE v2 | 改进 |
|------|--------|--------|------|
| 找到可行解 | 15-20 ep | 10-15 ep | **-33%** |
| 总episodes | 40-60 | 30-45 | **-25%** |
| 异常值处理 | ❌ | ✅ | **显著** |
| 指标偏科 | 可能 | 不可能 | **显著** |
| 稳定性 | 中等 | 高 | **显著** |

---

## 日志示例

```
[FRE v2] Phase 0 Ep 1: 可行解 ✅ | 连续成功 1/5
[FRE v2] Phase 0 Ep 5: 可行解 ✅ | 连续成功 5/5
[FRE v2] Phase 0 → 1 | Episodes: 5 | Reason: 连续成功，提前进入下一阶段

[FRE v2] Phase 1 Ep 1: 可行解 ✅ | 连续成功 1/5
[FRE v2] Phase 1 Ep 6: 检测到异常值 | 连续失败 1/10
[FRE v2] Phase 1 Ep 8: 可行解 ✅ | 连续成功 1/5
...
```

---

## 详细说明

见 `FRE_V2_GUIDE.md`
