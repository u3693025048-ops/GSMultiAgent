# 奖励函数 - 快速参考

## 核心公式

```
R = r_sep + r_peak_ny + [Phase B: r_hit_rate + r_sep_bonus + r_peak_ny_prog + r_pm + r_bw]

最终：R_final = clip(R, -10, 10)
```

## 五个指标的奖励项

| 指标 | 项名 | 公式 | 范围 | 说明 |
|------|------|------|------|------|
| SEP | r_sep | -clip(SEP/1000, 0, 10) | [-10, 0] | 绝对优先，两阶段都有 |
| PeakNy | r_peak_ny | -penalty × scale × overshoot | [-2.5, 0] | 软约束，两阶段都有 |
| 命中率 | r_hit_rate | 5.0 × (hit_rate/100) | [0, 5] | Phase B only |
| SEP低值 | r_sep_bonus | 3.0 (sep<2) ~ 0 (sep>5) | [0, 3] | Phase B only |
| PM | r_pm | 0.8 (in range) ~ -3.0 (out) | [-3, 0.8] | Phase B only, fine_scale衰减 |
| BW | r_bw | 0.5 (in range) ~ -2.0 (out) | [-2, 0.5] | Phase B only, fine_scale衰减 |

## 两个阶段

### Phase A：生存阶段（SEP > 500m）
- ✅ SEP项
- ✅ PeakNy项
- ❌ 其他项

**目标**：快速降低SEP

### Phase B：精细调优（SEP ≤ 500m）
- ✅ SEP项
- ✅ PeakNy项
- ✅ 命中率项
- ✅ SEP奖励项
- ✅ PM项 (fine_scale衰减)
- ✅ BW项 (fine_scale衰减)

**目标**：平衡多个目标

## 默认参数

```yaml
# SEP相关
sep_low_threshold: 2.0m
sep_low_bonus: 3.0
sep_mid_threshold: 5.0m
sep_mid_weight: 1.0
sep_survival_threshold: 500.0m

# PeakNy相关
peak_ny_max: 20.0g
peak_ny_penalty: 1.0
peak_ny_progressive_low: 15.0g

# PM相关
pm_min: 45.0°
pm_max: 65.0°
pm_bonus: 0.8
pm_penalty: 3.0

# BW相关
bw_min: 20.0 rad/s
bw_max: 85.0 rad/s
bw_bonus: 0.5
bw_penalty: 2.0

# 硬截断
hard_truncation_peak_g: 50.0g
```

## 奖励曲线速查

### SEP奖励
```
SEP = 0m   → r_sep = 0.0
SEP = 5m   → r_sep = -0.005
SEP = 10m  → r_sep = -0.01
SEP = 500m → r_sep = -0.5
```

### 命中率奖励
```
hit_rate = 80%  → r_hit_rate = 4.0
hit_rate = 92%  → r_hit_rate = 4.6
hit_rate = 100% → r_hit_rate = 5.0
```

### PM奖励 (fine_scale=1.0)
```
PM = 55°  → r_pm = +0.8 (目标范围)
PM = 40°  → r_pm = -0.33 (太低)
PM = 70°  → r_pm = -0.33 (太高)
PM = -10° → r_pm = -10.0 (不稳定)
```

### BW奖励 (fine_scale=1.0)
```
BW = 50 rad/s  → r_bw = +0.5 (目标范围)
BW = 10 rad/s  → r_bw = -0.24 (太低)
BW = 100 rad/s → r_bw = -0.35 (太高)
```

## 硬截断条件

```python
if peak_ny > 50.0 or isnan(SEP) or isinf(SEP) or isnan(peak_ny):
    return -10.0
```

## 典型奖励值

| 情况 | hit_rate | SEP | PeakNy | PM | BW | 奖励 |
|------|----------|-----|--------|----|----|------|
| 最优 | 95% | 3m | 18g | 55° | 50 | 7.4 |
| 可接受 | 92% | 6m | 20g | 50° | 40 | 6.2 |
| 不可接受 | 85% | 8m | 25g | 35° | 100 | 1.0 |
| 极端 | 80% | 15m | 55g | 20° | 10 | -10.0 |

## 调优建议

### RL收敛太慢
- ↑ `hit_rate` 权重
- ↑ `sep_low_bonus`
- ↓ `sep_survival_threshold`

### PeakNy超出
- ↑ `peak_ny_penalty`
- ↓ `peak_ny_max`
- ↑ `hard_truncation_peak_g`

### PM/BW不稳定
- ↑ `pm_bonus` / `bw_bonus`
- ↑ `pm_penalty` / `bw_penalty`
- 调整范围：`pm_min/pm_max` / `bw_min/bw_max`

## 代码位置

**文件**：`multi_agent/rl/matlab_rl_optimizer.py`  
**方法**：`_compute_reward()`  
**行号**：第1701-1825行

## 详细说明

见 `REWARD_FUNCTION.md`
