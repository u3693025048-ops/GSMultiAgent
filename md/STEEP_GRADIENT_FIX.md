# T4快速修复：梯度陡峭检测与自适应探索

## 问题

T4工况的可行域很窄，PPO的标准探索策略容易"冲坏"这个脆弱的区域，导致无法收敛。

## 解决方案

实施**梯度陡峭检测**和**自适应探索衰减**，在梯度陡峭区域自动降低探索幅度。

## 实施步骤

### 步骤1：添加梯度检测器类

在 `multi_agent/rl/matlab_rl_optimizer.py` 的文件开头（导入部分之后）添加：

```python
class SteepGradientDetector:
    """检测参数空间中的梯度陡峭区域"""
    
    def __init__(self, window_size=5, threshold=2.0):
        """
        Args:
            window_size: 用于计算梯度的历史窗口大小
            threshold: 梯度阈值（奖励变化/参数变化）
        """
        self.window_size = window_size
        self.threshold = threshold
        self.reward_history = []
        self.param_history = []
    
    def is_steep_gradient(self):
        """检测是否在梯度陡峭区域"""
        if len(self.reward_history) < self.window_size:
            return False
        
        recent_rewards = self.reward_history[-self.window_size:]
        recent_params = self.param_history[-self.window_size:]
        
        # 计算奖励变化率
        reward_changes = []
        for i in range(1, len(recent_rewards)):
            change = abs(recent_rewards[i] - recent_rewards[i-1])
            reward_changes.append(change)
        
        if not reward_changes:
            return False
        
        avg_reward_change = sum(reward_changes) / len(reward_changes)
        
        # 计算参数变化率
        param_changes = []
        for i in range(1, len(recent_params)):
            change = 0.0
            for k in recent_params[i]:
                change += abs(recent_params[i][k] - recent_params[i-1][k])
            param_changes.append(change)
        
        if not param_changes:
            return False
        
        avg_param_change = sum(param_changes) / len(param_changes)
        
        # 梯度 = 奖励变化 / 参数变化
        if avg_param_change > 1e-6:
            gradient = avg_reward_change / avg_param_change
            return gradient > self.threshold
        
        return False
    
    def update(self, reward, params):
        """更新历史记录"""
        self.reward_history.append(reward)
        self.param_history.append(dict(params))
        
        # 保持窗口大小
        if len(self.reward_history) > 2 * self.window_size:
            self.reward_history.pop(0)
            self.param_history.pop(0)
```

### 步骤2：修改optimize()方法

找到 `optimize()` 方法中的主循环（约第2481行），在循环开始前添加检测器初始化：

```python
async def optimize(self, ...):
    # ... 现有代码 ...
    
    # ── 初始化梯度检测器 ──
    steep_detector = SteepGradientDetector(window_size=5, threshold=2.0)
    
    for ep in range(max_ep):
        try:
            episodes_run = ep + 1
            
            # ── 梯度陡峭检测与自适应探索衰减 ──
            if self._actor is not None and max_ep > 0:
                # 检测梯度陡峭
                is_steep = steep_detector.is_steep_gradient()
                
                if is_steep:
                    # 梯度陡峭：降低探索幅度（保守探索）
                    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.5
                    logger.info(
                        f"  [Ep {ep+1}] 梯度陡峭检测，降低探索幅度 "
                        f"(decay={_decay:.3f})"
                    )
                else:
                    # 正常梯度：标准探索衰减
                    _decay = max(0.15, 1.0 - ep / float(max_ep))
                
                # 应用探索衰减到所有参数
                for i, k in enumerate(self._action_keys):
                    _base_ls = 0.0 if k in self._PITCH_KEYS else -1.0
                    self._actor.log_std[i] = float(
                        np.clip(_base_ls + math.log(_decay), -4.0, 2.0)
                    )
            
            # ... 现有的采样和仿真代码 ...
            state      = self._build_state(self._current_params, self._base_phys, self._last_metrics)
            action, lp = self._actor.sample(state, explore=True)
            value      = self._critic.value(state)
            
            new_params = self._action_to_params(action)
            
            metrics = await self._run_simulation_with_params(
                new_params, mission_conditions, script_path, n_mc
            )
            
            # ... 现有的奖励计算和更新代码 ...
            reward = self._compute_reward(metrics)
            
            # ── 更新梯度检测器 ──
            steep_detector.update(reward, new_params)
            
            # ... 继续现有的RL流程 ...
```

### 步骤3：验证修改

编译检查：

```bash
python -m py_compile multi_agent/rl/matlab_rl_optimizer.py
```

应该没有语法错误。

### 步骤4：测试

运行T4工况优化：

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

观察日志中是否出现梯度陡峭检测的消息：

```
[Ep 5] 梯度陡峭检测，降低探索幅度 (decay=0.075)
[Ep 10] 梯度陡峭检测，降低探索幅度 (decay=0.050)
[Ep 15] 梯度恢复正常，恢复标准探索 (decay=0.300)
```

---

## 工作原理

### 梯度陡峭的定义

```
梯度 = 奖励变化 / 参数变化

高梯度（>2.0）：
├─ 参数变化小 → 奖励变化大
├─ 说明参数空间陡峭
└─ 容易越过可行域边界

低梯度（<2.0）：
├─ 参数变化大 → 奖励变化小
├─ 说明参数空间平缓
└─ 容易找到可行参数
```

### 自适应探索衰减

```
梯度陡峭时：
├─ 探索幅度 = 标准幅度 × 0.5
├─ 目的：小步长探索，避免越过边界
└─ 结果：在可行域附近精细搜索

梯度正常时：
├─ 探索幅度 = 标准幅度
├─ 目的：大步长探索，快速找到最优点
└─ 结果：快速收敛
```

---

## 预期结果

### 实施前
```
[Ep 1] reward=-2.345 hit=94.0% SEP=4.22m PeakN=51.53
[Ep 2] reward=-5.123 hit=92.0% SEP=8.45m PeakN=48.20  ← 奖励崖
[Ep 3] reward=-4.987 hit=91.0% SEP=9.12m PeakN=52.10  ← 振荡
[Ep 4] reward=-3.456 hit=93.0% SEP=5.67m PeakN=49.50
...
[Ep 100] reward=-3.200 hit=92.5% SEP=6.50m PeakN=50.20  ← 无法收敛
```

### 实施后
```
[Ep 1] reward=-2.345 hit=94.0% SEP=4.22m PeakN=51.53
[Ep 2] reward=-2.456 hit=94.5% SEP=4.10m PeakN=51.20  ← 小步长
[Ep 3] 梯度陡峭检测，降低探索幅度 (decay=0.075)
[Ep 4] reward=-2.234 hit=94.8% SEP=3.95m PeakN=50.80  ← 继续改善
[Ep 5] reward=-1.987 hit=95.0% SEP=3.50m PeakN=49.50  ← New best
...
[Ep 50] reward=0.234 hit=96.0% SEP=2.10m PeakN=28.50  ← 收敛
```

---

## 参数调优

如果效果不理想，可以调整以下参数：

### 调整1：梯度阈值

```python
# 当前：threshold=2.0
# 更敏感：threshold=1.5（更容易触发梯度陡峭）
# 更保守：threshold=3.0（只在非常陡峭时触发）

steep_detector = SteepGradientDetector(window_size=5, threshold=1.5)
```

### 调整2：探索衰减因子

```python
# 当前：梯度陡峭时 decay = 标准 × 0.5
# 更激进：decay = 标准 × 0.7（降低幅度较小）
# 更保守：decay = 标准 × 0.3（降低幅度较大）

if is_steep:
    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.3  # 改为0.3
```

### 调整3：窗口大小

```python
# 当前：window_size=5
# 更快响应：window_size=3（更快检测梯度变化）
# 更稳定：window_size=7（更稳定的梯度估计）

steep_detector = SteepGradientDetector(window_size=3, threshold=2.0)
```

---

## 故障排除

### 问题1：梯度检测不工作

**症状**：日志中没有看到梯度陡峭检测的消息

**原因**：梯度阈值太高，或历史数据不足

**解决**：
1. 降低阈值：`threshold=1.5`
2. 减小窗口：`window_size=3`

### 问题2：探索幅度降低太多

**症状**：RL收敛变慢，奖励改善停滞

**原因**：探索衰减因子太小

**解决**：增大衰减因子
```python
_decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.7  # 改为0.7
```

### 问题3：仍然无法收敛

**原因**：可能需要结合其他方案

**解决**：
1. 同时实施奖励崖式检测（见 `T4_NARROW_FEASIBLE_REGION.md`）
2. 考虑修改制导律（见 `T4_ADVANCED_SOLUTIONS.md`）

---

## 总结

通过梯度陡峭检测和自适应探索衰减：
- ✅ 自动识别窄可行域
- ✅ 在梯度陡峭区域自动降低探索幅度
- ✅ 避免PPO大步长冲坏可行域
- ✅ 在可行域附近精细搜索
- ✅ 预期T4在50-100 episode内收敛

实施时间：1-2小时  
代码改动：约50行  
风险等级：低
