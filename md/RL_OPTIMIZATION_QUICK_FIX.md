# RL优化效率低 - 快速修复

## 问题症状

- 每轮优化结果比起始值变差
- 优化效率很低
- 指标无法改善

## 根本原因（7种）

| # | 原因 | 症状 | 权重 |
|---|------|------|------|
| 1 | SEP项权重过大 | 命中率、PM、BW无法改善 | ⭐⭐⭐⭐⭐ |
| 2 | 生存阶段阈值不当 | 长期停留在生存阶段 | ⭐⭐⭐⭐ |
| 3 | 奖励函数不连续 | 优化不稳定 | ⭐⭐⭐ |
| 4 | 初始参数选择不当 | 早期优化很慢 | ⭐⭐⭐⭐ |
| 5 | 奖励权重配置不合理 | 某些指标被忽视 | ⭐⭐⭐⭐ |
| 6 | 参数探索范围过大 | 优化不稳定 | ⭐⭐⭐ |
| 7 | 发散检测过度 | 陷入局部最优 | ⭐⭐ |

## 快速诊断

### 查看日志

```
Baseline reward=X.XXX
Episode 1: reward=Y.YYY
Episode 2: reward=Z.ZZZ
```

**分析**：
- reward < baseline_reward? → 优化在变差
- reward波动很大? → 探索噪声过大
- reward停留不变? → 陷入局部最优

### 检查指标变化

```
Episode 1: hit_rate=85%, SEP=8m, PM=40°
Episode 2: hit_rate=84%, SEP=9m, PM=38°
Episode 3: hit_rate=83%, SEP=10m, PM=36°
```

**分析**：
- 所有指标都变差? → SEP项权重过大
- 只有某些指标变差? → 那些指标的权重太小

## 快速修复（按优先级）

### 修复1：增加命中率权重 ⭐⭐⭐⭐⭐

**问题**：命中率无法改善

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    hit_rate: 8.0  # 从 5.0 → 8.0
```

**预期效果**：+20-30% 优化效率

### 修复2：降低生存阶段阈值 ⭐⭐⭐⭐

**问题**：长期停留在生存阶段，其他指标无法优化

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    sep_survival_threshold: 300.0  # 从 500.0 → 300.0
```

**预期效果**：+15-25% 优化效率

### 修复3：增加PM/BW权重 ⭐⭐⭐

**问题**：PM/BW无法进入目标范围

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    pm_bonus: 1.5      # 从 0.8 → 1.5
    pm_penalty: 5.0    # 从 3.0 → 5.0
    bw_bonus: 1.0      # 从 0.5 → 1.0
    bw_penalty: 3.0    # 从 2.0 → 3.0
```

**预期效果**：+10-20% 优化效率

### 修复4：降低探索噪声 ⭐⭐⭐

**问题**：优化不稳定，参数变化太大

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  pitch_log_std: -1.0   # 从 -0.7 → -1.0
  other_log_std: -2.0   # 从 -1.6 → -2.0
```

**预期效果**：+10-15% 优化效率

### 修复5：使用历史参数 ⭐⭐⭐⭐

**问题**：初始参数太差，早期优化很慢

**修改**：`cli_agent.py`

```python
# 从PE中获取历史参数
initial_params = parameter_experience.get_best_params(
    task_prompt=task_prompt,
    top_k=1
)

rl_result = await rl_optimizer.optimize(
    script_path=script_path,
    mission_conditions=mission_conditions,
    initial_auto_params=initial_params,  # 使用历史参数
)
```

**预期效果**：+30-50% 优化效率

## 完整调优步骤

### 步骤1：诊断（5分钟）
1. 查看日志
2. 分析奖励项贡献
3. 检查参数和指标变化

### 步骤2：修复（5分钟）
1. 根据诊断选择修复方案
2. 修改 `config.yaml`
3. 重新运行优化

### 步骤3：验证（10分钟）
1. 检查奖励是否上升
2. 检查指标是否改善
3. 检查优化是否稳定

### 步骤4：微调（可选）
1. 如果改善不够，增加权重
2. 如果波动太大，降低噪声
3. 如果收敛太慢，调整阈值

## 常见问题速查

| 问题 | 原因 | 修复 |
|------|------|------|
| 命中率无法改善 | hit_rate权重太小 | ↑ hit_rate (5→8) |
| SEP无法进一步降低 | sep_survival_threshold太大 | ↓ sep_survival_threshold (500→300) |
| PM/BW超出范围 | PM/BW权重太小 | ↑ pm_bonus/bw_bonus |
| 优化不稳定 | 探索噪声太大 | ↑ pitch_log_std (-0.7→-1.0) |
| 初期优化很慢 | 初始参数太差 | 使用PE历史参数 |
| 陷入局部最优 | 发散惩罚太强 | ↑ diverge_reward_threshold (-9.5→-8) |
| 所有指标变差 | SEP项权重压制 | ↓ sep_survival_threshold或↑其他权重 |

## 默认参数参考

```yaml
matlab_rl_optimizer:
  # 当前默认值
  reward_weights:
    hit_rate: 5.0
    sep_low_bonus: 3.0
    sep_low_threshold: 2.0
    sep_mid_threshold: 5.0
    sep_survival_threshold: 500.0
    peak_ny_max: 20.0
    peak_ny_penalty: 1.0
    pm_bonus: 0.8
    pm_min: 45.0
    pm_max: 65.0
    pm_penalty: 3.0
    bw_bonus: 0.5
    bw_min: 20.0
    bw_max: 85.0
    bw_penalty: 2.0
  
  # 推荐调优值
  pitch_log_std: -1.0      # 从 -0.7
  other_log_std: -2.0      # 从 -1.6
```

## 详细说明

见 `RL_OPTIMIZATION_DIAGNOSIS.md`
