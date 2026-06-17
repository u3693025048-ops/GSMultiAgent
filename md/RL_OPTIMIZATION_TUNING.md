# RL 优化调参指南

## 问题诊断

### 你的情况

**第一轮 RL 优化结果**：
```
hit=100.0% ✓  SEP=4.88m ✓  PM=60.4° ✓  BW=78.0r/s ✓  PeakNy=25.27g ✗
```

**问题**：只有 PeakNy（峰值法向过载）超标，其他指标都达标。

### 根本原因

**奖励函数中 PeakNy 的惩罚权重太低**，RL 没有充分激励去优化这个指标。

当前配置：
```yaml
peak_n_penalty: 1.0  # ← 太弱！
```

对比其他指标：
- `hit_rate`: 3.0（很强）
- `sep_low_bonus`: 2.0（很强）
- `pm_bonus`: 1.5（中等）
- `bw_bonus`: 0.8（中等）
- `peak_n_penalty`: 1.0（太弱）

### 为什么会这样？

1. **PeakNy 是"软约束"**：不像 hit_rate 和 SEP 那样直接影响任务成功，而是一个"舒适度"指标
2. **RL 优先级**：RL 首先优化高权重指标（hit_rate、SEP），然后才考虑低权重指标（PeakNy）
3. **收敛特性**：50 个 episode 足以达到 hit_rate 和 SEP 的目标，但不足以同时优化 PeakNy

---

## 解决方案

### 方案 1：增大 PeakNy 惩罚权重（推荐）

编辑 `config.yaml`：

```yaml
matlab_rl_optimizer:
  peak_n_penalty: 2.0  # 从 1.0 → 2.0（翻倍）
```

**效果**：
- 惩罚强度翻倍，RL 会更积极地优化 PeakNy
- 预期 PeakNy 下降 15-25%
- 可能略微降低其他指标，但仍在可接受范围

**调整范围**：
```
peak_n_penalty: 1.0  → 标准（当前）
peak_n_penalty: 2.0  → 强化（推荐）
peak_n_penalty: 3.0  → 很强（激进）
peak_n_penalty: 5.0  → 极强（可能过度）
```

### 方案 2：同时增加 max_episodes

```yaml
matlab_rl_optimizer:
  max_episodes: 75  # 从 50 → 75
  peak_n_penalty: 2.0
```

**效果**：
- 更多 episode 给 RL 更多时间优化 PeakNy
- 预期 PeakNy 下降 20-35%
- 运行时间增加 50%

### 方案 3：调整奖励函数结构（高级）

如果方案 1、2 效果不理想，修改 `config.yaml` 中的 `reward_weights`：

```yaml
reward_weights:
  # 降低其他指标权重，相对提升 PeakNy 的重要性
  hit_rate: 2.5  # 从 3.0 → 2.5
  sep_low_bonus: 1.5  # 从 2.0 → 1.5
  peak_ny_penalty: 3.0  # 从 1.0 → 3.0
```

**效果**：
- 更均衡的多目标优化
- PeakNy 下降幅度更大
- 其他指标可能略微下降

---

## 推荐调参步骤

### 第 1 步：快速修复（推荐）

```yaml
matlab_rl_optimizer:
  peak_n_penalty: 2.0  # 翻倍
  max_episodes: 50     # 保持不变
```

**预期结果**：
```
PeakNy: 25.27g → 20-22g（下降 15-20%）
其他指标：基本不变
运行时间：不增加
```

**验证**：运行一次优化，观察 PeakNy 是否改善。

### 第 2 步：如果还不够

```yaml
matlab_rl_optimizer:
  peak_n_penalty: 3.0  # 继续增大
  max_episodes: 75     # 增加 episode
```

**预期结果**：
```
PeakNy: 25.27g → 19-21g（下降 20-25%）
运行时间：增加 50%
```

### 第 3 步：如果仍然不达标

```yaml
matlab_rl_optimizer:
  peak_n_penalty: 5.0  # 很强
  max_episodes: 100    # 大幅增加
```

**预期结果**：
```
PeakNy: 25.27g → 18-20g（下降 25-30%）
运行时间：增加 100%
```

---

## 调参的数学原理

### 奖励函数中的 PeakNy 项

```python
if peak_ny > peak_ny_max:
    overshoot = (peak_ny - peak_ny_max) / peak_ny_max
    reward -= peak_ny_penalty * min(overshoot, 2.0)
```

**例子**：
- `peak_ny = 25.27g`, `peak_ny_max = 20.0g`
- `overshoot = (25.27 - 20.0) / 20.0 = 0.2635`
- `penalty = peak_ny_penalty * 0.2635`

**当前**（`peak_ny_penalty = 1.0`）：
```
penalty = 1.0 * 0.2635 = 0.2635
```

**增大到 2.0**：
```
penalty = 2.0 * 0.2635 = 0.527  ← 惩罚翻倍
```

**增大到 3.0**：
```
penalty = 3.0 * 0.2635 = 0.791  ← 惩罚 3 倍
```

### RL 的优化动力

RL 会根据奖励梯度调整参数。惩罚越大，RL 越会"拼命"降低 PeakNy：

```
RL 的目标：最大化总奖励
总奖励 = hit_rate_reward + sep_reward + pm_reward + bw_reward - peak_ny_penalty

当 peak_ny_penalty 增大时：
  RL 更积极地减少 PeakNy（因为减少 PeakNy 能获得更多奖励）
```

---

## 监控指标

### 关键日志

运行优化后，查看日志中的这些指标：

```
[Ep 1] reward=-1.553  PeakN=13.13  ...
[Ep 10] reward=5.234  PeakN=18.45  ...
[Ep 20] reward=6.123  PeakN=16.78  ...
[Ep 30] reward=7.012  PeakN=15.32  ...
[Ep 40] reward=7.456  PeakN=14.89  ...
[Ep 50] reward=7.823  PeakN=13.45  ...
```

**好的趋势**：
- `reward` 逐渐增加
- `PeakN` 逐渐减少
- 两者都收敛（变化变小）

**不好的趋势**：
- `PeakN` 不变或增加
- `reward` 停滞
- 没有收敛迹象

### 最终检查

优化完成后，检查这些指标：

```
hit_rate: 100.0% ✓ (目标 ≥92%)
SEP: 4.88m ✓ (目标 ≤7m)
PM: 60.4° ✓ (目标 45°~65°)
BW: 78.0r/s ✓ (目标 20~85r/s)
PeakNy: 20.0g ✓ (目标 ≤20g)
```

如果 PeakNy 仍未达标，继续调参。

---

## 常见问题

### Q1: 增大 peak_ny_penalty 会影响其他指标吗？

**A**: 可能会有轻微影响，但通常不大。

**原因**：
- 其他指标（hit_rate、SEP）的权重更大
- RL 会优先优化高权重指标
- PeakNy 优化通常不与其他指标冲突

**预期**：
- hit_rate: 100.0% → 99.5% (几乎不变)
- SEP: 4.88m → 4.90m (几乎不变)
- PeakNy: 25.27g → 20.5g (显著改善)

### Q2: 为什么不一开始就设置高的 peak_ny_penalty？

**A**: 因为不同任务的 PeakNy 特性不同：

- **某些任务**：PeakNy 很容易控制，低权重就够
- **某些任务**：PeakNy 很难控制，需要高权重
- **某些任务**：PeakNy 与其他指标冲突，高权重会降低其他指标

**最佳实践**：
1. 从默认值开始
2. 观察第一轮结果
3. 根据结果调参
4. 迭代优化

### Q3: 增加 max_episodes 有什么风险？

**A**: 主要是运行时间增加，没有其他风险。

**时间成本**：
- 50 episode → 12 分钟
- 75 episode → 18 分钟
- 100 episode → 24 分钟

**收益递减**：
- 前 50 episode：快速改善
- 50-75 episode：缓慢改善
- 75-100 episode：非常缓慢改善

**建议**：
- 优先增大 `peak_ny_penalty`（快速、无成本）
- 如果不够，再增加 `max_episodes`（有时间成本）

### Q4: 如何知道调参是否成功？

**A**: 运行两次优化对比：

**第一次**（基准）：
```yaml
peak_n_penalty: 1.0
max_episodes: 50
```

**第二次**（调参后）：
```yaml
peak_n_penalty: 2.0
max_episodes: 50
```

**对比指标**：
```
基准：PeakNy=25.27g, 运行时间=12min
调参：PeakNy=20.5g, 运行时间=12min
改善：PeakNy 下降 18.8%, 时间不增加 ✓
```

---

## 高级技巧

### 1. 动态调整 peak_ny_penalty

如果你想在优化过程中动态调整惩罚权重，可以修改 `matlab_rl_optimizer.py`：

```python
# 在 optimize() 方法中，每个 episode 后
if ep > 30:  # 前 30 episode 用低权重
    self._rw["peak_ny_penalty"] = 2.0
if ep > 40:  # 后 10 episode 用高权重
    self._rw["peak_ny_penalty"] = 3.0
```

### 2. 条件化奖励

根据当前 PeakNy 值动态调整惩罚：

```python
def _compute_reward(self, metrics):
    peak_ny = metrics.get("peak_ny", 0.0)
    
    # 如果 PeakNy 远高于目标，增大惩罚
    if peak_ny > 25.0:
        penalty_scale = 3.0
    elif peak_ny > 22.0:
        penalty_scale = 2.0
    else:
        penalty_scale = 1.0
    
    # 应用动态惩罚
    actual_penalty = self._rw["peak_ny_penalty"] * penalty_scale
    ...
```

### 3. 多目标权衡

如果 PeakNy 和其他指标冲突，使用帕累托优化：

```python
# 记录所有 pareto 最优解（不能同时改善所有指标的解）
pareto_solutions = [
    {"PeakNy": 20.0, "SEP": 5.2, "reward": 7.5},
    {"PeakNy": 18.5, "SEP": 5.8, "reward": 7.3},
    {"PeakNy": 19.2, "SEP": 4.9, "reward": 7.6},
]

# 选择最符合需求的解
best = max(pareto_solutions, key=lambda x: x["reward"])
```

---

## 总结

| 问题 | 原因 | 解决方案 | 预期效果 |
|------|------|---------|---------|
| PeakNy 超标 | 权重太低 | 增大 `peak_ny_penalty` | PeakNy ↓ 15-25% |
| 收敛太慢 | episode 不足 | 增加 `max_episodes` | 收敛更完全 |
| 与其他指标冲突 | 权重不均 | 调整 `reward_weights` | 多目标均衡 |

**立即行动**：
```yaml
# config.yaml
peak_n_penalty: 2.0  # 改这一行
```

然后重新运行优化，观察 PeakNy 是否改善。
