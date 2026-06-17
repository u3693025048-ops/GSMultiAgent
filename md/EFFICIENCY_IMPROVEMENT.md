# RL 优化效率改进指南

## 问题诊断

你的优化效率仍然很低，主要原因：

### 1. **PeakNy 权重配置不当**
- 当前：`peak_n_penalty: 1.0`（太弱）
- 问题：RL 优先优化高权重指标（hit_rate、SEP），低权重指标（PeakNy）被忽视
- 结果：50 个 episode 后，PeakNy 仍然超标（25.27g > 20g）

### 2. **Episode 数不足**
- 当前：`max_episodes: 50`
- 问题：9 维参数空间需要更多 episode 才能充分探索
- 结果：参数空间探索不充分，收敛不完全

### 3. **AMRO 参数配置不优**
- 当前：`gradient_threshold: 0.5`（可能太高）
- 问题：跳变检测灵敏度不足，禁区标记不充分
- 结果：虽然检测到跳变，但没有充分利用这个信息

---

## 改进方案（已应用）

### 改进 1：增强 PeakNy 约束

```yaml
# 从
peak_n_penalty: 1.0

# 改为
peak_n_penalty: 2.5  # 翻倍 2.5 倍
```

**效果**：
- RL 会更积极地优化 PeakNy
- 预期 PeakNy 下降 25-35%
- 其他指标基本不变

**原理**：
```python
# 当前（peak_n_penalty=1.0）
penalty = 1.0 * (25.27-20.0)/20.0 = 0.264

# 改进后（peak_n_penalty=2.5）
penalty = 2.5 * (25.27-20.0)/20.0 = 0.659  ← 惩罚增加 2.5 倍
```

### 改进 2：增加 Episode 数

```yaml
# 从
max_episodes: 50

# 改为
max_episodes: 75  # 增加 50%
```

**效果**：
- RL 有更多时间优化所有指标
- 预期收敛更完全，指标更稳定
- 运行时间增加 50%（约 12min → 18min）

**权衡**：
- 优化质量 ↑↑（更重要）
- 运行时间 ↑（可接受）

### 改进 3：优化 AMRO 参数

```yaml
# 跳变检测灵敏度
amro_gradient_threshold: 0.4  # 从 0.5 → 0.4（更敏感）

# 禁区大小
amro_forbidden_zone_radius: 0.2  # 从 0.15 → 0.2（更大）

# 历史窗口
amro_history_window: 8  # 从 10 → 8（更敏感）
```

**效果**：
- 更容易检测到跳变
- 禁区更大，避免重复探索
- 预期优化效率提升 30-50%

---

## 预期改进效果

| 指标 | 改进前 | 改进后 | 改善 |
|------|--------|--------|------|
| **PeakNy** | 25.27g | 19-21g | ↓ 20-25% |
| **Episode 数** | 50 | 75 | ↑ 50% |
| **运行时间** | 12 min | 18 min | ↑ 50% |
| **优化效率** | 100% | 85-90% | ↓ 10-15% |
| **收敛质量** | 一般 | 很好 | ↑↑ |

**说明**：
- 优化效率略降（因为 episode 增加，探索更充分）
- 但收敛质量大幅提升（所有指标都能达标）

---

## 立即行动

### 步骤 1：确认配置已更新

检查 `config.yaml` 中的这些值：

```yaml
max_episodes: 75                      # ✓ 已改
peak_n_penalty: 2.5                   # ✓ 已改
amro_gradient_threshold: 0.4           # ✓ 已改
amro_forbidden_zone_radius: 0.2        # ✓ 已改
amro_history_window: 8                 # ✓ 已改
```

### 步骤 2：重新运行优化

```bash
python cli_agent.py --file prompt.txt
```

### 步骤 3：观察结果

优化完成后，检查这些指标：

```
hit_rate: 100.0% ✓
SEP: 4.88m ✓
PM: 60.4° ✓
BW: 78.0r/s ✓
PeakNy: 20.0g ✓  ← 关键指标，应该 ≤20g
```

如果 PeakNy 仍未达标，继续调整：

```yaml
peak_n_penalty: 3.0  # 继续增大
max_episodes: 100    # 继续增加
```

---

## 深入分析

### 为什么优化效率低？

**优化效率 = 有效 episode / 总 episode**

当前情况：
- 总 episode = 50
- 有效 episode ≈ 50（100% 效率）
- 但收敛不完全（PeakNy 超标）

**问题**：虽然没有浪费 episode（效率 100%），但 episode 总数不足以达到所有目标。

**解决**：
1. 增加 episode 数（75 → 100）
2. 增强 PeakNy 权重（1.0 → 2.5）
3. 优化 AMRO 参数（更敏感的检测）

### AMRO 的作用

AMRO 检测到了 1 个跳变（zeta2 参数），但：
- 没有标记禁区（可能因为跳变不够严重）
- 没有充分利用这个信息加速优化

**改进**：
- 降低 `gradient_threshold`（0.5 → 0.4）→ 更容易检测跳变
- 增大 `forbidden_zone_radius`（0.15 → 0.2）→ 禁区更大，避免重复探索
- 减小 `history_window`（10 → 8）→ 更敏感的梯度计算

---

## 监控指标

### 日志中的关键信息

运行优化时，注意这些日志：

```
[AMRO] 自适应多区域优化已启用 | 梯度阈值=0.4 | 禁区半径=0.2 | 历史窗口=8
[AMRO] 跳变检测 @ Ep X: 参数 XXX=... 奖励下降 ... (严重度=...)
[AMRO 统计] 总 episode=75 | 跳变检测=? | 禁区数=? | 已探索区域=? | 优化效率=?
```

**预期**：
- 跳变检测数 ↑（更敏感）
- 禁区数 ↑（禁区更大）
- 已探索区域 ↑（episode 更多）
- 优化效率 ↓（但收敛更完全）

### 性能指标日志

```
[Ep 1] reward=-1.553  PeakN=13.13  ...
[Ep 25] reward=5.234  PeakN=18.45  ...
[Ep 50] reward=6.123  PeakN=16.78  ...
[Ep 75] reward=7.456  PeakN=14.89  ...  ← 应该继续下降
```

**好的趋势**：
- `reward` 逐渐增加
- `PeakN` 逐渐减少
- 两者都在收敛

---

## 如果仍然不够

如果改进后 PeakNy 仍未达标，继续调整：

### 方案 A：进一步增强 PeakNy 约束

```yaml
peak_n_penalty: 3.0  # 从 2.5 → 3.0
```

### 方案 B：增加更多 Episode

```yaml
max_episodes: 100  # 从 75 → 100
```

### 方案 C：同时调整

```yaml
peak_n_penalty: 3.0
max_episodes: 100
amro_gradient_threshold: 0.3  # 更敏感
```

### 方案 D：调整奖励函数结构

如果上述方案都不够，修改 `reward_weights`：

```yaml
reward_weights:
  hit_rate: 2.5        # 从 3.0 → 2.5（降低）
  sep_low_bonus: 1.5   # 从 2.0 → 1.5（降低）
  peak_ny_penalty: 3.0 # 从 1.0 → 3.0（提升）
```

这样会相对提升 PeakNy 的重要性。

---

## 总结

| 改进项 | 改前 | 改后 | 效果 |
|--------|------|------|------|
| **peak_n_penalty** | 1.0 | 2.5 | PeakNy ↓ 20-25% |
| **max_episodes** | 50 | 75 | 收敛更完全 |
| **gradient_threshold** | 0.5 | 0.4 | 跳变检测更敏感 |
| **forbidden_zone_radius** | 0.15 | 0.2 | 禁区更大 |
| **history_window** | 10 | 8 | 梯度计算更敏感 |

**预期结果**：
- ✅ PeakNy: 25.27g → 19-21g
- ✅ 其他指标：基本不变
- ✅ 收敛质量：大幅提升
- ✅ 运行时间：增加 50%（可接受）

**立即行动**：配置已更新，直接运行优化即可。
