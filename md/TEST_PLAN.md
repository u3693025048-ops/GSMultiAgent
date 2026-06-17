# T4工况测试计划

## 快速开始

### 步骤1：验证代码修改

```bash
cd c:\Users\Lenovo\Desktop\SCI1\code\code\xiao\GSMultiAgent13-V0.2
python -m py_compile multi_agent/rl/matlab_rl_optimizer.py
```

**预期**：无错误输出

---

### 步骤2：运行T4工况优化

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

**预期运行时间**：30-60分钟（取决于MATLAB/Octave速度）

---

## 观察指标

### 关键日志消息

在运行过程中，观察以下日志消息：

#### 1. 初始化消息
```
[RL] Contextual-bandit PPO | batch=64 | nmc=10 | gamma=0 | entropy_coef=0.05
Evaluating baseline (PE-retrieved / script params)…
Baseline reward=-2.345  metrics={...}
```

**说明**：RL优化器已初始化，梯度检测器已创建

#### 2. 梯度陡峭检测消息
```
[Ep 5] Steep gradient detected, reducing exploration (decay=0.075)
[Ep 10] Steep gradient detected, reducing exploration (decay=0.050)
```

**说明**：梯度检测器工作正常，自动降低探索幅度

#### 3. 奖励改善消息
```
[Ep 1] reward=-2.345 hit=94.0% SEP=4.22m ...
[Ep 5] reward=-1.987 hit=95.2% SEP=3.50m ...
[Ep 10] reward=-1.432 hit=96.0% SEP=2.50m ...
[Ep 50] reward=0.234 hit=96.5% SEP=2.10m ...
```

**说明**：奖励稳定改善，没有大幅振荡

---

## 成功标准

### ✅ 方案1有效的标志

1. **梯度检测工作**
   - 日志中出现"Steep gradient detected"消息
   - 至少在5个episode后出现

2. **探索衰减生效**
   - decay值在梯度陡峭时降低（例如0.075, 0.050）
   - decay值在梯度正常时恢复（例如0.300, 0.400）

3. **奖励稳定改善**
   - 奖励逐步改善，不出现大幅下降
   - 50-100 episode内收敛到正值

4. **快速收敛**
   - T4在50-100 episode内收敛
   - 比之前的无法收敛有明显改善

### ❌ 方案1无效的标志

1. **梯度检测不工作**
   - 日志中从未出现"Steep gradient detected"
   - 说明梯度阈值设置不当

2. **奖励仍然振荡**
   - 奖励在-5到-2之间反复波动
   - 没有明显的改善趋势

3. **无法收敛**
   - 100 episode后仍未收敛
   - 最终状态仍为"success"而非"task_requirements_met"

---

## 详细检查清单

### 检查1：代码修改验证

- [ ] `SteepGradientDetector` 类已添加（第40-101行）
- [ ] `steep_detector` 初始化（第2550行）
- [ ] 自适应探索衰减逻辑（第2557-2575行）
- [ ] 梯度检测器更新（第2674行）

### 检查2：运行时行为

- [ ] 初始化日志出现
- [ ] 梯度检测消息出现（至少5个episode后）
- [ ] 奖励逐步改善
- [ ] 没有异常错误

### 检查3：收敛结果

- [ ] 最终奖励 > 0（理想情况）
- [ ] 最终奖励 > -2.0（可接受）
- [ ] Episode数 < 100（快速收敛）
- [ ] 状态为"task_requirements_met"或"success"

---

## 预期结果对比

### 实施前（无方案1）

```
Baseline reward=-2.345

[Ep 1] reward=-2.345 hit=94.0% SEP=4.22m
[Ep 2] reward=-5.123 hit=92.0% SEP=8.45m  ← 奖励崖
[Ep 3] reward=-4.987 hit=91.0% SEP=9.12m  ← 振荡
[Ep 4] reward=-3.456 hit=93.0% SEP=5.67m
[Ep 5] reward=-4.234 hit=92.5% SEP=7.89m  ← 无法恢复
...
[Ep 100] reward=-3.200 hit=92.5% SEP=6.50m  ← 无法收敛

Status: success (但实际上没有满足要求)
```

### 实施后（有方案1）

```
Baseline reward=-2.345

[Ep 1] reward=-2.345 hit=94.0% SEP=4.22m
[Ep 2] reward=-2.456 hit=94.5% SEP=4.10m
[Ep 3] reward=-2.234 hit=94.8% SEP=3.95m
[Ep 4] reward=-2.123 hit=95.0% SEP=3.80m
[Ep 5] Steep gradient detected, reducing exploration (decay=0.075)
[Ep 6] reward=-1.987 hit=95.2% SEP=3.50m  ← 继续改善
[Ep 7] reward=-1.856 hit=95.5% SEP=3.20m
[Ep 8] Steep gradient detected, reducing exploration (decay=0.050)
[Ep 9] reward=-1.654 hit=95.8% SEP=2.90m
[Ep 10] reward=-1.432 hit=96.0% SEP=2.50m
...
[Ep 50] reward=0.234 hit=96.5% SEP=2.10m  ← 收敛到正值

Status: task_requirements_met (成功!)
```

---

## 故障排除

### 情况1：梯度检测不工作

**症状**：
- 日志中没有"Steep gradient detected"消息
- 奖励仍然振荡

**调试步骤**：

1. 检查梯度阈值是否太高
   ```python
   # 在 optimize() 方法中，改为：
   steep_detector = SteepGradientDetector(window_size=5, threshold=1.5)
   ```

2. 检查窗口大小是否太大
   ```python
   # 改为：
   steep_detector = SteepGradientDetector(window_size=3, threshold=2.0)
   ```

3. 运行更多episode观察
   ```bash
   python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m" --max_episodes 150
   ```

### 情况2：探索幅度降低太多

**症状**：
- RL收敛变慢
- 奖励改善停滞

**调试步骤**：

1. 增大衰减因子
   ```python
   # 在 optimize() 方法中，改为：
   if is_steep:
       _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.7  # 改为0.7
   ```

2. 重新运行优化
   ```bash
   python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
   ```

### 情况3：仍然无法收敛

**原因**：可能需要结合其他方案

**解决方案**：
1. 实施方案2（奖励崖式检测）
2. 修改制导律（见T4_ADVANCED_SOLUTIONS.md）
3. 扩展RL参数搜索空间

---

## 数据收集

### 记录运行结果

运行完成后，记录以下信息：

```
运行日期：2026-06-05
工况：T4
方案：方案1（梯度陡峭检测）

初始状态：
- Baseline reward: -2.345
- Baseline hit: 94.0%
- Baseline SEP: 4.22m

最终状态：
- Best reward: [记录]
- Best hit: [记录]%
- Best SEP: [记录]m
- Total episodes: [记录]

梯度检测：
- 首次检测episode: [记录]
- 总检测次数: [记录]
- 最小decay: [记录]

收敛情况：
- 是否收敛: [是/否]
- 收敛episode: [记录]
- 最终状态: [记录]

日志文件：[保存路径]
```

---

## 后续步骤

### 如果方案1成功 ✅

1. **验证结果**
   - 确认T4满足要求
   - 检查其他工况是否受影响

2. **优化参数**
   - 调整梯度阈值以获得最佳性能
   - 记录最优参数

3. **文档更新**
   - 更新项目文档
   - 记录成功案例

### 如果方案1不够 ⚠️

1. **调整参数**
   - 尝试不同的梯度阈值
   - 尝试不同的衰减因子

2. **实施方案2**
   - 添加奖励崖式检测
   - 结合两个方案使用

3. **考虑其他方案**
   - 修改制导律（方案1-3）
   - 扩展RL参数空间（方案5）

---

## 联系与支持

如有问题，请参考：
- `STEEP_GRADIENT_FIX.md` - 实施指南
- `T4_NARROW_FEASIBLE_REGION.md` - 技术细节
- `T4_FEASIBLE_REGION_SUMMARY.md` - 完整方案总结

---

**准备好开始测试了吗？** 🚀

运行以下命令开始T4工况优化：
```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

祝你成功！
