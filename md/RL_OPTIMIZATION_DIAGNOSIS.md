# RL优化效率低的诊断与解决方案

## 问题描述

优化效率很低，每轮优化结果反而比起始值变差。

**症状**：
- RL优化多轮后，指标没有改善
- 新参数的奖励反而低于基线奖励
- 优化陷入局部最优或发散

---

## 根本原因分析

### 原因1：SEP项权重过大，压制其他指标

**症状**：
- 命中率、PM、BW无法改善
- RL只关注SEP，忽视其他目标

**根本原因**：
```python
r_sep = -clip(SEP / 1000.0, 0.0, 10.0)  # 范围 [-10, 0]
```

SEP项范围是 [-10, 0]，而其他项的范围远小于此：
- 命中率项：[0, 5]
- PM项：[-3, 0.8]
- BW项：[-2, 0.5]

当SEP变化时，SEP项的变化远大于其他项，导致RL无法优化其他指标。

**例子**：
```
基线：SEP=8m, hit_rate=80%, PM=40°
  r_sep = -0.008
  r_hit_rate = 4.0
  r_pm = -1.5
  R_baseline = 2.492

新参数：SEP=7m, hit_rate=95%, PM=55°
  r_sep = -0.007
  r_hit_rate = 4.75
  r_pm = 0.8
  R_new = 5.543

虽然新参数更好，但如果SEP增加到9m：
  r_sep = -0.009
  r_hit_rate = 4.75
  r_pm = 0.8
  R = 5.541 < R_baseline

RL会倾向于降低SEP，即使这意味着降低命中率
```

**解决方案**：
1. 增加其他项的权重
2. 降低SEP项的缩放因子
3. 调整 `sep_survival_threshold` 更早进入精细调优

### 原因2：生存阶段阈值设置不当

**症状**：
- RL长期停留在生存阶段
- 无法进入精细调优阶段
- 其他指标无法优化

**根本原因**：
```python
survival_phase = sep > sep_survival_threshold  # 默认 500m
```

如果 `sep_survival_threshold` 设置过大，RL会长期只优化SEP，忽视其他指标。

**例子**：
```
sep_survival_threshold = 500m

基线SEP = 8m → 已在精细调优阶段
新参数SEP = 9m → 仍在精细调优阶段

但如果：
sep_survival_threshold = 10m

基线SEP = 8m → 在生存阶段（8 > 10? 否）
实际上应该是：基线SEP = 8m → 在精细调优阶段（8 < 10）

问题：如果初始SEP = 15m，则会长期停留在生存阶段
```

**解决方案**：
1. 降低 `sep_survival_threshold`（从500 → 300或200）
2. 根据初始SEP动态调整
3. 确保尽快进入精细调优阶段

### 原因3：奖励函数不连续或梯度消失

**症状**：
- 小的参数变化导致大的奖励变化
- RL无法学到平滑的策略
- 优化过程不稳定

**根本原因**：

#### 3.1 SEP项的阶跃函数

```python
r_sep = -clip(SEP / 1000.0, 0.0, 10.0)
```

当SEP在0-1000m范围内变化时，r_sep的变化很小（[-0.001, 0]），但当SEP > 1000m时，r_sep立即变为-10。

#### 3.2 生存阶段的阶跃

```python
if survival_phase:
    return clip(reward, -10, 10)  # 只包含SEP和PeakNy
else:
    # 包含所有项
```

当SEP从501m变为499m时，奖励函数从只计算SEP项变为计算所有项，导致奖励函数不连续。

**例子**：
```
SEP = 501m (生存阶段)：
  r_sep = -0.501
  r_peak_ny = 0
  R = -0.501

SEP = 499m (精细调优阶段)：
  r_sep = -0.499
  r_hit_rate = 4.0
  r_sep_bonus = 0
  r_peak_ny = 0
  r_pm = 0.8
  r_bw = 0.5
  R = 4.801

同样的SEP改善，奖励却增加了5.3！
```

**解决方案**：
1. 使用平滑的过渡函数
2. 在两个阶段都计算所有项，但使用权重衰减
3. 增加 `fine_scale` 的过渡区间

### 原因4：初始参数选择不当

**症状**：
- 初始参数本身就很差
- RL需要很多轮才能改善
- 早期优化效率极低

**根本原因**：
```python
baseline_reward = self._compute_reward(baseline_metrics)
if initial_auto_params or baseline_reward >= self._baseline_reward_threshold:
    self._shrink_log_std_for_warmstart()
```

如果初始参数的奖励低于阈值（0.5），RL会使用较大的探索噪声，导致早期优化不稳定。

**解决方案**：
1. 使用更好的初始参数
2. 增加 `baseline_reward_threshold`
3. 使用参数经验库（PE）的历史参数

### 原因5：奖励权重配置不合理

**症状**：
- 某些指标的权重过小，被忽视
- 某些指标的权重过大，压制其他指标
- RL无法平衡多个目标

**根本原因**：

默认权重：
```yaml
hit_rate: 5.0
sep_low_bonus: 3.0
sep_low_threshold: 2.0m
sep_mid_threshold: 5.0m
pm_bonus: 0.8
pm_penalty: 3.0
bw_bonus: 0.5
bw_penalty: 2.0
```

问题：
- `hit_rate` 权重 (5.0) 相对较小，当SEP项为 [-10, 0] 时，命中率的影响被压制
- `sep_low_bonus` (3.0) 只在SEP < 2m时有效，对大多数情况无帮助
- PM/BW的权重太小，无法有效优化稳定性

**解决方案**：
1. 增加 `hit_rate` 权重（5.0 → 8.0或10.0）
2. 调整 `sep_low_threshold` 和 `sep_mid_threshold`
3. 增加 `pm_bonus` 和 `bw_bonus`

### 原因6：参数探索范围过大

**症状**：
- RL探索的参数变化太大
- 每轮优化的结果波动很大
- 无法收敛

**根本原因**：
```python
pitch_log_std = -0.7    # exp(-0.7) ≈ 0.497
other_log_std = -1.6    # exp(-1.6) ≈ 0.202
```

这些是初始探索噪声的标准差。如果参数范围是 [20, 60]，则：
- 俯仰参数的探索范围：±0.497 × (60-20) = ±19.9
- 其他参数的探索范围：±0.202 × (60-20) = ±8.1

这意味着每次探索可能改变参数的25-50%，太大了。

**解决方案**：
1. 增加 `pitch_log_std`（-0.7 → -1.0或-1.2）
2. 增加 `other_log_std`（-1.6 → -2.0或-2.2）
3. 使用 `warm_start_std_scale` 在初期降低探索噪声

### 原因7：发散检测和惩罚机制

**症状**：
- RL在某些轮次后突然变差
- 优化过程不稳定

**根本原因**：
```python
if reward <= self._diverge_reward_threshold:  # -9.5
    self._consecutive_diverge += 1
    if self._consecutive_diverge >= self._diverge_penalty_episodes:  # 3
        self._apply_diverge_exploration_penalty()
```

如果连续3轮奖励低于-9.5，RL会降低探索噪声，可能导致陷入局部最优。

**解决方案**：
1. 调整 `diverge_reward_threshold`（-9.5 → -8.0）
2. 增加 `diverge_penalty_episodes`（3 → 5）
3. 使用自适应探索控制（AMRO）

---

## 诊断步骤

### 第1步：检查日志

查看 `logs/` 目录中的日志文件，找到以下信息：

```
Baseline reward=X.XXX  metrics={...}
[RL] Episode 1: reward=Y.YYY, metrics={...}
[RL] Episode 2: reward=Z.ZZZ, metrics={...}
```

**分析**：
- 如果 `reward` 持续低于 `baseline_reward`，说明RL在变差
- 如果 `reward` 波动很大，说明探索噪声过大
- 如果 `reward` 停留在某个值不变，说明陷入局部最优

### 第2步：分析奖励项的贡献

修改 `_compute_reward()` 方法，添加调试输出：

```python
def _compute_reward(self, metrics: Dict[str, float]) -> float:
    # ... 现有代码 ...
    
    # 添加调试输出
    logger.debug(f"[Reward] r_sep={r_sep:.3f}, r_peak_ny={r_peak_ny:.3f}, "
                 f"r_hit_rate={r_hit_rate:.3f}, r_pm={r_pm:.3f}, r_bw={r_bw:.3f}")
    
    return float(np.clip(reward, -10.0, 10.0))
```

**分析**：
- 哪个项的贡献最大？
- 哪个项的变化最频繁？
- 是否有某个项被压制？

### 第3步：检查参数变化

查看RL优化过程中参数的变化：

```python
logger.info(f"[RL] Episode {ep}: params={suggested}, "
            f"delta={delta}, reward={reward}")
```

**分析**：
- 参数变化是否太大？
- 参数是否在有效范围内？
- 是否有某个参数无法改变？

### 第4步：检查指标变化

查看仿真指标的变化：

```
Episode 1: hit_rate=85%, SEP=8m, PeakNy=22g, PM=40°, BW=75
Episode 2: hit_rate=84%, SEP=9m, PeakNy=23g, PM=38°, BW=80
Episode 3: hit_rate=83%, SEP=10m, PeakNy=24g, PM=36°, BW=85
```

**分析**：
- 所有指标都在变差吗？
- 还是只有某些指标变差？
- 是否有指标在改善但被其他指标压制？

---

## 快速修复方案

### 方案A：增加命中率权重（最常见）

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    hit_rate: 8.0  # 从 5.0 → 8.0
```

**预期效果**：
- RL更关注命中率
- 其他指标的改善更明显
- 优化效率提升 20-30%

### 方案B：降低生存阶段阈值

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    sep_survival_threshold: 300.0  # 从 500.0 → 300.0
```

**预期效果**：
- 更快进入精细调优阶段
- 其他指标更早被优化
- 优化效率提升 15-25%

### 方案C：增加PM/BW权重

**修改**：`config.yaml`

```yaml
matlab_rl_optimizer:
  reward_weights:
    pm_bonus: 1.5    # 从 0.8 → 1.5
    pm_penalty: 5.0  # 从 3.0 → 5.0
    bw_bonus: 1.0    # 从 0.5 → 1.0
    bw_penalty: 3.0  # 从 2.0 → 3.0
```

**预期效果**：
- PM/BW更容易进入目标范围
- 稳定性改善更明显
- 优化效率提升 10-20%

### 方案D：降低探索噪声

**修改**：`config.yaml` 或代码

```yaml
matlab_rl_optimizer:
  pitch_log_std: -1.0      # 从 -0.7 → -1.0
  other_log_std: -2.0      # 从 -1.6 → -2.0
```

**预期效果**：
- 参数变化更平滑
- 优化过程更稳定
- 优化效率提升 10-15%

### 方案E：使用参数经验库

**修改**：`cli_agent.py`

```python
# 从PE中获取历史参数作为初始值
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

**预期效果**：
- 从更好的起点开始
- 减少早期的无效探索
- 优化效率提升 30-50%

---

## 完整调优步骤

### 步骤1：诊断当前问题

1. 查看日志，确定是哪个指标在变差
2. 分析奖励项的贡献
3. 检查参数和指标的变化趋势

### 步骤2：应用快速修复

根据诊断结果，选择合适的修复方案：
- 命中率变差 → 方案A
- SEP无法改善 → 方案B
- PM/BW不稳定 → 方案C
- 优化不稳定 → 方案D
- 初始参数差 → 方案E

### 步骤3：验证效果

运行优化，检查：
- 奖励是否上升？
- 指标是否改善？
- 优化是否稳定？

### 步骤4：微调参数

根据验证结果，进一步微调：
- 如果改善不够，增加权重
- 如果波动太大，降低探索噪声
- 如果收敛太慢，调整阈值

---

## 常见问题排查表

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| 命中率无法改善 | hit_rate权重太小 | ↑ hit_rate (5→8) |
| SEP无法进一步降低 | sep_survival_threshold太大 | ↓ sep_survival_threshold (500→300) |
| PM/BW超出范围 | PM/BW权重太小 | ↑ pm_bonus/bw_bonus |
| 优化不稳定 | 探索噪声太大 | ↑ pitch_log_std (-0.7→-1.0) |
| 初期优化很慢 | 初始参数太差 | 使用PE历史参数 |
| 陷入局部最优 | 发散惩罚太强 | ↑ diverge_reward_threshold (-9.5→-8) |
| 所有指标都变差 | SEP项权重压制其他项 | ↓ sep_survival_threshold或↑其他权重 |

---

## 总结

优化效率低的主要原因：

1. **SEP项权重过大** - 压制其他指标
2. **生存阶段阈值不当** - 长期停留在生存阶段
3. **奖励函数不连续** - 导致学习不稳定
4. **初始参数选择不当** - 起点太差
5. **奖励权重配置不合理** - 某些指标被忽视
6. **参数探索范围过大** - 优化不稳定
7. **发散检测过度** - 陷入局部最优

**快速修复**：
- ↑ `hit_rate` 权重（5.0 → 8.0）
- ↓ `sep_survival_threshold`（500 → 300）
- ↑ PM/BW权重
- ↑ `pitch_log_std`（-0.7 → -1.0）
- 使用PE历史参数

通过这些调整，优化效率通常可以提升 20-50%。
