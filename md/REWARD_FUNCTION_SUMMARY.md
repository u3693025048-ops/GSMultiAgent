# 奖励函数 - 完整总结

## 概述

优化算法的奖励函数是RL强化学习的核心，定义了什么样的参数组合是"好的"。

**位置**：`multi_agent/rl/matlab_rl_optimizer.py` 第1701-1825行  
**方法**：`_compute_reward(metrics: Dict[str, float]) -> float`

---

## 核心设计原则

### 1. 分阶段优化

```
生存阶段 (SEP > 500m)
    ↓
快速降低SEP，忽略其他指标
    ↓
精细调优阶段 (SEP ≤ 500m)
    ↓
平衡多个目标，逐步优化PM/BW
```

### 2. 多目标加权

五个关键指标：
- **SEP** (命中距离) - 绝对优先
- **命中率** (Hit Rate) - 主要目标
- **PeakNy** (峰值过载) - 软约束
- **PM** (相位裕度) - 稳定性指标
- **BW** (带宽) - 响应速度指标

### 3. 硬截断保护

```python
if peak_ny > 50g or isnan(SEP) or isinf(SEP):
    return -10.0  # 最低奖励，快速排除
```

### 4. 动态缩放

PM/BW项随SEP改善逐步加入：
```python
fine_scale = max(0, 1 - sep/500)
```

---

## 奖励函数详解

### Phase A：生存阶段（SEP > 500m）

**目标**：快速改善SEP到可接受范围

**包含项**：
1. **SEP项** (绝对优先)
   ```
   r_sep = -clip(SEP/1000, 0, 10)
   范围：[-10, 0]
   ```

2. **PeakNy约束**
   ```
   if peak_ny > peak_ny_max:
       r_peak_ny = -penalty × scale × min(overshoot, 2.0)
   范围：[-2.5, 0]
   ```

**返回**：`clip(r_sep + r_peak_ny, -10, 10)`

### Phase B：精细调优阶段（SEP ≤ 500m）

**目标**：在满足SEP的前提下，优化其他指标

**包含项**：

1. **SEP项** (基础)
   ```
   r_sep = -clip(SEP/1000, 0, 10)
   ```

2. **命中率项** (主导)
   ```
   r_hit_rate = 5.0 × (hit_rate / 100)
   范围：[0, 5]
   ```

3. **SEP奖励项** (加速)
   ```
   if sep < 2m:
       r_sep_bonus = 3.0
   elif sep < 5m:
       r_sep_bonus = 1.0 × (1 - (sep-2)/(5-2))
   else:
       r_sep_bonus = 0
   范围：[0, 3]
   ```

4. **PeakNy约束** (同Phase A)
   ```
   r_peak_ny = -penalty × scale × min(overshoot, 2.0)
   ```

5. **PM项** (逐步加入)
   ```
   fine_scale = max(0, 1 - sep/500)
   
   if 45° ≤ pm ≤ 65°:
       r_pm = 0.8 × fine_scale
   elif pm < 0:
       r_pm = -3.0 × fine_scale × (3 + |pm|/15)
   else:
       r_pm = -3.0 × fine_scale × min(5, dist_pm/45)
   范围：[-3, 0.8]
   ```

6. **BW项** (逐步加入)
   ```
   fine_scale = max(0, 1 - sep/500)
   
   if 20 ≤ bw ≤ 85:
       r_bw = 0.5 × fine_scale
   else:
       r_bw = -2.0 × fine_scale × min(5, dist_bw/85)
   范围：[-2, 0.5]
   ```

**返回**：`clip(r_sep + r_peak_ny + r_hit_rate + r_sep_bonus + r_peak_ny_prog + r_pm + r_bw, -10, 10)`

---

## 参数配置

### 默认参数表

| 参数 | 默认值 | 说明 |
|------|--------|------|
| **SEP相关** | | |
| sep_low_threshold | 2.0m | SEP低值阈值 |
| sep_low_bonus | 3.0 | SEP低值奖励 |
| sep_mid_threshold | 5.0m | SEP中值阈值 |
| sep_mid_weight | 1.0 | SEP中值权重 |
| sep_survival_threshold | 500.0m | 生存阶段阈值 |
| **PeakNy相关** | | |
| peak_ny_max | 20.0g | PeakNy目标最大值 |
| peak_ny_penalty | 1.0 | PeakNy超出惩罚系数 |
| peak_ny_progressive_low | 15.0g | PeakNy渐进下界 |
| **PM相关** | | |
| pm_min | 45.0° | PM最小值 |
| pm_max | 65.0° | PM最大值 |
| pm_bonus | 0.8 | PM目标范围奖励 |
| pm_penalty | 3.0 | PM超出惩罚系数 |
| **BW相关** | | |
| bw_min | 20.0 rad/s | BW最小值 |
| bw_max | 85.0 rad/s | BW最大值 |
| bw_bonus | 0.5 | BW目标范围奖励 |
| bw_penalty | 2.0 | BW超出惩罚系数 |
| **硬截断** | | |
| hard_truncation_peak_g | 50.0g | 硬截断PeakNy阈值 |

### 在config.yaml中配置

```yaml
matlab_rl_optimizer:
  peak_n_max: 20.0
  peak_n_penalty: 1.0
  reward_weights:
    hit_rate: 5.0
    sep_low_bonus: 3.0
    sep_low_threshold: 2.0
    sep_mid_weight: 1.0
    sep_mid_threshold: 5.0
    sep_survival_threshold: 500.0
    peak_ny_max: 20.0
    peak_ny_penalty: 1.0
    peak_ny_progressive_low: 15.0
    pm_bonus: 0.8
    pm_min: 45.0
    pm_max: 65.0
    pm_penalty: 3.0
    bw_bonus: 0.5
    bw_min: 20.0
    bw_max: 85.0
    bw_penalty: 2.0
    hard_truncation_peak_g: 50.0
```

---

## 典型奖励值

### 最优情况
```
hit_rate = 95%, SEP = 3m, peak_ny = 18g, PM = 55°, BW = 50 rad/s
R = 7.4
```

### 可接受情况
```
hit_rate = 92%, SEP = 6m, peak_ny = 20g, PM = 50°, BW = 40 rad/s
R = 6.2
```

### 不可接受情况
```
hit_rate = 85%, SEP = 8m, peak_ny = 25g, PM = 35°, BW = 100 rad/s
R = 1.0
```

### 极端情况（硬截断）
```
peak_ny = 55g 或 SEP = NaN
R = -10.0
```

---

## 调优指南

### 问题1：RL收敛太慢

**症状**：RL需要很多轮才能找到好的参数

**原因**：奖励信号不够强，RL探索效率低

**解决方案**：
1. 增加 `hit_rate` 权重（从5.0→8.0）
2. 增加 `sep_low_bonus`（从3.0→5.0）
3. 降低 `sep_survival_threshold`（从500→300）

### 问题2：PeakNy超出

**症状**：RL不断尝试增加参数导致PeakNy > 20g

**原因**：PeakNy惩罚不够强

**解决方案**：
1. 增加 `peak_ny_penalty`（从1.0→2.0）
2. 降低 `peak_ny_max`（从20→18）
3. 增加 `hard_truncation_peak_g`（从50→40）

### 问题3：PM/BW不稳定

**症状**：PM或BW在目标范围外波动

**原因**：PM/BW项权重不够或范围设置不合理

**解决方案**：
1. 增加 `pm_bonus`（从0.8→1.5）
2. 增加 `pm_penalty`（从3.0→5.0）
3. 调整 `pm_min/pm_max`（从45-65→40-70）

### 问题4：SEP无法进一步降低

**症状**：SEP卡在某个值无法继续改善

**原因**：SEP奖励曲线可能不够激励

**解决方案**：
1. 增加 `sep_low_bonus`（从3.0→4.0）
2. 降低 `sep_low_threshold`（从2.0→1.5）
3. 增加 `sep_mid_weight`（从1.0→2.0）

---

## 奖励函数流程图

```
输入：metrics (hit_rate, SEP, peak_ny, pitch_PM, pitch_BW)
  ↓
[硬截断检查]
  peak_ny > 50g? → 返回 -10.0
  SEP NaN/Inf?  → 返回 -10.0
  ↓ (通过)
[计算基础项]
  r_sep = -clip(SEP/1000, 0, 10)
  r_peak_ny = 计算PeakNy惩罚
  ↓
[判断阶段]
  SEP > 500m? → Phase A (生存)
  ↓ (否)
[Phase B: 精细调优]
  r_hit_rate = 5.0 × (hit_rate/100)
  r_sep_bonus = 计算SEP奖励
  r_peak_ny_prog = 计算PeakNy渐进
  fine_scale = max(0, 1 - sep/500)
  r_pm = 计算PM项 × fine_scale
  r_bw = 计算BW项 × fine_scale
  ↓
[求和并裁剪]
  R = r_sep + r_peak_ny + [Phase B项]
  R_final = clip(R, -10, 10)
  ↓
输出：R_final
```

---

## 关键特性总结

✅ **分阶段设计**
- 生存阶段：快速降低SEP
- 精细调优：平衡多个目标

✅ **多目标加权**
- SEP绝对优先
- 命中率主导
- PM/BW逐步加入

✅ **硬截断保护**
- 防止极端参数
- 快速排除不可行方案

✅ **动态缩放**
- PM/BW随SEP改善逐步加入
- 避免在SEP仍然很大时被欺骗

✅ **完全可配置**
- 所有参数都可调整
- 支持config.yaml配置
- 支持代码中动态配置

---

## 文档导航

- **快速参考**：`REWARD_FUNCTION_QUICK.md`
- **详细说明**：`REWARD_FUNCTION.md`
- **本文档**：`REWARD_FUNCTION_SUMMARY.md`

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `multi_agent/rl/matlab_rl_optimizer.py` | 奖励函数实现 |
| `config.yaml` | 奖励权重配置 |
| `md/REWARD_FUNCTION.md` | 详细文档 |
| `md/REWARD_FUNCTION_QUICK.md` | 快速参考 |
| `tests/test_matlab_rl_optimizer.py` | 单元测试 |
