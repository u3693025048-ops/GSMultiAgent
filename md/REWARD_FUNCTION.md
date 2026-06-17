# 优化算法的奖励函数

## 概述

优化算法（PPO强化学习）的奖励函数定义在 `multi_agent/rl/matlab_rl_optimizer.py` 的 `_compute_reward()` 方法中。

**核心特点**：
- **分阶段设计**：根据SEP值分为"生存阶段"和"精细调优阶段"
- **多目标加权**：综合考虑命中率、SEP、PeakNy、PM、BW五个指标
- **硬截断保护**：对极端情况（PeakNy > 50g或SEP NaN/Inf）直接返回最低奖励
- **动态缩放**：PM/BW项随SEP改善逐步加入，避免在SEP仍然很大时被欺骗

---

## 奖励函数结构

### 1. 硬截断（Hard Truncation）

```python
if (
    (peak_ny > 50.0)  # 过载过大
    or isnan(SEP)     # SEP无效
    or isinf(SEP)     # SEP无穷大
    or isnan(peak_ny) # 过载无效
):
    return HARD_REWARD_PENALTY = -10.0
```

**目的**：
- 防止RL探索导致系统发散的参数
- 快速排除不可行的参数组合

---

### 2. SEP绝对优先项

```python
r_sep = -clip(SEP / 1000.0, 0.0, 10.0)
reward += r_sep
```

**特点**：
- SEP是最关键的指标（命中率的前提）
- 负项：SEP越大，奖励越低
- 范围：[-10.0, 0.0]（SEP从0到10000m）
- 无论哪个阶段都包含此项

**例子**：
- SEP = 0m   → r_sep = 0.0
- SEP = 5m   → r_sep = -0.005
- SEP = 10m  → r_sep = -0.01
- SEP = 500m → r_sep = -0.5

---

### 3. PeakNy软约束（两阶段都有）

```python
if peak_ny > peak_ny_max:
    overshoot = (peak_ny - peak_ny_max) / peak_ny_max
    if overshoot < 0.2:
        penalty_scale = 1.0
    elif overshoot < 0.5:
        penalty_scale = 1.5
    else:
        penalty_scale = 2.5
    reward -= peak_ny_penalty * penalty_scale * min(overshoot, 2.0)
```

**特点**：
- 渐进式惩罚：超出越多，惩罚越重
- 三档缩放：轻微超出(1.0x) → 中等超出(1.5x) → 严重超出(2.5x)
- 默认参数：`peak_ny_max=20.0`, `peak_ny_penalty=1.0`

**例子**（peak_ny_max=20g, peak_ny_penalty=1.0）：
- peak_ny = 18g  → 无惩罚
- peak_ny = 22g  → overshoot=0.1, penalty = 1.0 × 1.0 × 0.1 = -0.1
- peak_ny = 24g  → overshoot=0.2, penalty = 1.0 × 1.0 × 0.2 = -0.2
- peak_ny = 30g  → overshoot=0.5, penalty = 1.0 × 1.5 × 0.5 = -0.75
- peak_ny = 40g  → overshoot=1.0, penalty = 1.0 × 2.5 × 1.0 = -2.5

---

### 4. 生存阶段（Phase A）

**触发条件**：`SEP > sep_survival_threshold`（默认500m）

**包含项**：
- ✅ SEP项
- ✅ PeakNy项
- ❌ 命中率项
- ❌ PM项
- ❌ BW项

**目的**：强制RL首先改善SEP，不被其他指标分散注意力

**返回**：
```python
return clip(reward, -10.0, 10.0)
```

---

### 5. 精细调优阶段（Phase B）

**触发条件**：`SEP <= sep_survival_threshold`（默认500m）

#### 5.1 命中率项

```python
reward += hit_rate_weight * (hit_rate / 100.0)
```

**参数**：
- `hit_rate_weight = 5.0`（默认）

**范围**：[0.0, 5.0]

**例子**：
- hit_rate = 80% → +4.0
- hit_rate = 92% → +4.6
- hit_rate = 100% → +5.0

#### 5.2 SEP低值奖励

```python
if sep < sep_low_threshold:
    reward += sep_low_bonus
elif sep < sep_mid_threshold:
    reward += sep_mid_weight * (1.0 - (sep - sep_low_threshold) / (sep_mid_threshold - sep_low_threshold))
```

**参数**（默认）：
- `sep_low_threshold = 2.0m`
- `sep_low_bonus = 3.0`
- `sep_mid_threshold = 5.0m`
- `sep_mid_weight = 1.0`

**奖励曲线**：
- sep < 2m   → +3.0（最大奖励）
- sep = 3.5m → +1.5（线性衰减）
- sep = 5m   → 0.0（不再奖励）
- sep > 5m   → 0.0（无额外奖励）

#### 5.3 PeakNy渐进引导

```python
if peak_ny_progressive_low <= peak_ny <= peak_ny_max:
    reward += 0.5 * (peak_ny_max - peak_ny) / (peak_ny_max - peak_ny_progressive_low)
elif peak_ny > peak_ny_max:
    reward += 0.05 * max(-1.0, (peak_ny_max - peak_ny) / peak_ny_max)
```

**参数**（默认）：
- `peak_ny_progressive_low = 15.0g`
- `peak_ny_max = 20.0g`

**奖励曲线**：
- peak_ny = 15g → +0.5（最大奖励）
- peak_ny = 17.5g → +0.25（线性衰减）
- peak_ny = 20g → 0.0（目标值）
- peak_ny = 25g → -0.25（轻微惩罚）

#### 5.4 相位裕度（PM）项

```python
fine_scale = max(0.0, 1.0 - sep / max(sep_survival_threshold, 1.0))

if pm_min <= pitch_pm <= pm_max:
    reward += pm_bonus * fine_scale
elif pitch_pm < 0:
    reward -= pm_penalty * fine_scale * (3.0 + abs(pitch_pm) / 15.0)
else:
    dist_pm = max(pm_min - pitch_pm, pitch_pm - pm_max, 0.0)
    reward -= pm_penalty * fine_scale * min(5.0, dist_pm / max(pm_min, 1.0))
```

**参数**（默认）：
- `pm_min = 45.0°`
- `pm_max = 65.0°`
- `pm_bonus = 0.8`
- `pm_penalty = 3.0`

**奖励曲线**（fine_scale=1.0时）：
- PM = 55° → +0.8（目标范围内）
- PM = 40° → -3.0 × (45-40)/45 = -0.33（低于最小值）
- PM = 70° → -3.0 × (70-65)/45 = -0.33（高于最大值）
- PM = -10° → -3.0 × (3.0 + 10/15) = -10.0（不稳定）

**fine_scale衰减**：
- SEP = 0m   → fine_scale = 1.0（PM项全力）
- SEP = 250m → fine_scale = 0.5（PM项减半）
- SEP = 500m → fine_scale = 0.0（PM项消失）

#### 5.5 带宽（BW）项

```python
if bw_min <= pitch_bw <= bw_max:
    reward += bw_bonus * fine_scale
else:
    dist_bw = max(bw_min - pitch_bw, pitch_bw - bw_max, 0.0)
    reward -= bw_penalty * fine_scale * min(5.0, dist_bw / max(bw_max, 1.0))
```

**参数**（默认）：
- `bw_min = 20.0 rad/s`
- `bw_max = 85.0 rad/s`
- `bw_bonus = 0.5`
- `bw_penalty = 2.0`

**奖励曲线**（fine_scale=1.0时）：
- BW = 50 rad/s → +0.5（目标范围内）
- BW = 10 rad/s → -2.0 × (20-10)/85 = -0.24（太低）
- BW = 100 rad/s → -2.0 × (100-85)/85 = -0.35（太高）

---

## 完整奖励公式

```
R = r_sep + r_peak_ny + [r_hit_rate + r_sep_bonus + r_peak_ny_prog + r_pm + r_bw]

其中：
  r_sep = -clip(SEP/1000, 0, 10)
  
  r_peak_ny = {
    -penalty_scale × min(overshoot, 2.0)  if peak_ny > peak_ny_max
    0                                       otherwise
  }
  
  [Phase B only]:
    r_hit_rate = 5.0 × (hit_rate / 100)
    r_sep_bonus = {
      3.0                                   if sep < 2.0
      1.0 × (1 - (sep-2)/(5-2))            if 2.0 <= sep < 5.0
      0                                     otherwise
    }
    r_peak_ny_prog = {
      0.5 × (20-peak_ny)/(20-15)           if 15 <= peak_ny <= 20
      0.05 × max(-1, (20-peak_ny)/20)      if peak_ny > 20
      0                                     otherwise
    }
    r_pm = fine_scale × {
      0.8                                   if 45 <= pm <= 65
      -3.0 × (3 + |pm|/15)                 if pm < 0
      -3.0 × min(5, dist_pm/45)            otherwise
    }
    r_bw = fine_scale × {
      0.5                                   if 20 <= bw <= 85
      -2.0 × min(5, dist_bw/85)            otherwise
    }
    
    fine_scale = max(0, 1 - sep/500)

最终奖励：R_final = clip(R, -10, 10)
```

---

## 配置参数

### 在config.yaml中配置

```yaml
matlab_rl_optimizer:
  # 奖励权重
  reward_weights:
    hit_rate: 5.0                    # 命中率权重
    sep_low_bonus: 3.0               # SEP低值奖励
    sep_low_threshold: 2.0           # SEP低值阈值 (m)
    sep_mid_weight: 1.0              # SEP中值权重
    sep_mid_threshold: 5.0           # SEP中值阈值 (m)
    sep_survival_threshold: 500.0    # 生存阶段阈值 (m)
    
    peak_ny_max: 20.0                # PeakNy目标最大值 (g)
    peak_ny_penalty: 1.0             # PeakNy超出惩罚系数
    peak_ny_progressive_low: 15.0    # PeakNy渐进下界 (g)
    
    pm_bonus: 0.8                    # PM目标范围奖励
    pm_min: 45.0                     # PM最小值 (°)
    pm_max: 65.0                     # PM最大值 (°)
    pm_penalty: 3.0                  # PM超出惩罚系数
    
    bw_bonus: 0.5                    # BW目标范围奖励
    bw_min: 20.0                     # BW最小值 (rad/s)
    bw_max: 85.0                     # BW最大值 (rad/s)
    bw_penalty: 2.0                  # BW超出惩罚系数
    
    hard_truncation_peak_g: 50.0     # 硬截断PeakNy阈值 (g)
    baseline_reset_peak_g: 40.0      # 基线重置PeakNy阈值 (g)
```

### 在代码中配置

```python
rl_optimizer = MatlabRLOptimizer(
    ...,
    peak_n_max=20.0,           # PeakNy目标最大值
    peak_n_penalty=1.0,        # PeakNy超出惩罚系数
    reward_weights={
        "hit_rate": 5.0,
        "sep_low_bonus": 3.0,
        "sep_low_threshold": 2.0,
        "sep_mid_weight": 1.0,
        "sep_mid_threshold": 5.0,
        "sep_survival_threshold": 500.0,
        "peak_ny_max": 20.0,
        "peak_ny_penalty": 1.0,
        "peak_ny_progressive_low": 15.0,
        "pm_bonus": 0.8,
        "pm_min": 45.0,
        "pm_max": 65.0,
        "pm_penalty": 3.0,
        "bw_bonus": 0.5,
        "bw_min": 20.0,
        "bw_max": 85.0,
        "bw_penalty": 2.0,
        "hard_truncation_peak_g": 50.0,
        "baseline_reset_peak_g": 40.0,
    },
)
```

---

## 优化策略

### 阶段1：生存阶段（SEP > 500m）

**目标**：快速改善SEP到可接受范围

**奖励构成**：
- SEP项（负，主导）
- PeakNy项（约束）

**RL策略**：
- 专注于降低SEP
- 忽略命中率、PM、BW
- 快速探索参数空间

### 阶段2：精细调优阶段（SEP ≤ 500m）

**目标**：在满足SEP的前提下，优化其他指标

**奖励构成**：
- SEP项（负，基础）
- 命中率项（正，主导）
- SEP奖励项（正，加速）
- PeakNy项（约束）
- PM项（正，逐步加入）
- BW项（正，逐步加入）

**RL策略**：
- 平衡多个目标
- 逐步优化PM和BW
- 避免PeakNy超出

---

## 典型奖励值

### 最优情况

```
hit_rate = 95%
SEP = 3m
peak_ny = 18g
pitch_PM = 55°
pitch_BW = 50 rad/s

r_sep = -0.003
r_peak_ny = 0
r_hit_rate = 4.75
r_sep_bonus = 1.0
r_peak_ny_prog = 0.4
r_pm = 0.8
r_bw = 0.5
fine_scale = 0.994

R = -0.003 + 0 + 4.75 + 1.0 + 0.4 + 0.8 + 0.5 = 7.447
```

### 可接受情况

```
hit_rate = 92%
SEP = 6m
peak_ny = 20g
pitch_PM = 50°
pitch_BW = 40 rad/s

r_sep = -0.006
r_peak_ny = 0
r_hit_rate = 4.6
r_sep_bonus = 0.33
r_peak_ny_prog = 0
r_pm = 0.8
r_bw = 0.5
fine_scale = 0.988

R = -0.006 + 0 + 4.6 + 0.33 + 0 + 0.8 + 0.5 = 6.224
```

### 不可接受情况

```
hit_rate = 85%
SEP = 8m
peak_ny = 25g
pitch_PM = 35°
pitch_BW = 100 rad/s

r_sep = -0.008
r_peak_ny = -0.75 (超出25%)
r_hit_rate = 4.25
r_sep_bonus = 0
r_peak_ny_prog = -0.25
r_pm = -1.5 (超出范围)
r_bw = -0.7 (超出范围)
fine_scale = 0.984

R = -0.008 + (-0.75) + 4.25 + 0 + (-0.25) + (-1.5) + (-0.7) = 1.042
```

---

## 调优建议

### 如果RL收敛太慢

**问题**：RL需要很多轮才能找到好的参数

**解决方案**：
1. 增加 `hit_rate` 权重（鼓励命中率）
2. 增加 `sep_low_bonus`（鼓励低SEP）
3. 降低 `sep_survival_threshold`（更快进入精细调优）

### 如果PeakNy超出

**问题**：RL不断尝试增加参数导致PeakNy过大

**解决方案**：
1. 增加 `peak_ny_penalty`（更重的惩罚）
2. 降低 `peak_ny_max`（更严格的约束）
3. 增加 `hard_truncation_peak_g`（更早硬截断）

### 如果PM/BW不稳定

**问题**：PM或BW在目标范围外波动

**解决方案**：
1. 增加 `pm_bonus` 或 `bw_bonus`（更强的奖励）
2. 增加 `pm_penalty` 或 `bw_penalty`（更强的惩罚）
3. 调整 `pm_min/pm_max` 或 `bw_min/bw_max`（放宽范围）

---

## 总结

**关键特点**：
- ✅ 分阶段设计：先生存后精细
- ✅ 多目标加权：综合考虑五个指标
- ✅ 硬截断保护：防止极端参数
- ✅ 动态缩放：PM/BW随SEP改善逐步加入
- ✅ 可配置：所有参数都可调整

**优化流程**：
1. 生存阶段：快速降低SEP
2. 精细调优：平衡多个目标
3. 收敛：找到最优参数组合
