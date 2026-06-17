# T4工况：窄可行域的RL探索策略

## 问题诊断

T4工况存在**"接近可行"的区域，但比T1-T3窄得多，也更容易被PPO探索冲坏**。

```
参数空间特性对比：

T1-T3（低频机动）：
├─ 可行域：宽阔，容错性强
├─ 梯度：平缓，容易优化
├─ 探索：标准PPO足以
└─ 结果：快速收敛

T4（高频机动）：
├─ 可行域：狭窄，容错性弱
├─ 梯度：陡峭，容易掉出可行域
├─ 探索：标准PPO容易"冲坏"
└─ 结果：无法收敛或振荡
```

### 为什么T4的可行域更窄？

1. **高频机动的物理约束**
   - 高频响应要求：w1, zeta1必须在很窄的范围内
   - 过高：过载爆炸（PeakNy > 50g）
   - 过低：无法跟踪目标（命中率下降）
   - 可行范围：可能只有全范围的10-20%

2. **多目标冲突**
   - PeakNy和PM的目标冲突
   - 降低PeakNy → PM升高
   - 降低PM → PeakNy升高
   - 可行域是这两个约束的交集（更窄）

3. **梯度陡峭**
   - 参数变化小 → 指标变化大
   - 容易越过可行域边界
   - 一旦越过，奖励崖式下降

---

## 解决方案

### 方案1：自适应探索衰减 ⭐⭐⭐ 推荐

**思路**：根据奖励变化情况，动态调整探索幅度

#### 1.1 检测"梯度陡峭"区域

```python
class SteepGradientDetector:
    def __init__(self, window_size=5, threshold=2.0):
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
        reward_changes = [abs(recent_rewards[i] - recent_rewards[i-1]) 
                         for i in range(1, len(recent_rewards))]
        avg_reward_change = sum(reward_changes) / len(reward_changes)
        
        # 计算参数变化率
        param_changes = []
        for i in range(1, len(recent_params)):
            change = sum(abs(recent_params[i][k] - recent_params[i-1][k]) 
                        for k in recent_params[i].keys())
            param_changes.append(change)
        avg_param_change = sum(param_changes) / len(param_changes)
        
        # 梯度 = 奖励变化 / 参数变化
        if avg_param_change > 1e-6:
            gradient = avg_reward_change / avg_param_change
            return gradient > self.threshold
        
        return False
    
    def update(self, reward, params):
        self.reward_history.append(reward)
        self.param_history.append(params.copy())
        if len(self.reward_history) > 2 * self.window_size:
            self.reward_history.pop(0)
            self.param_history.pop(0)
```

#### 1.2 动态调整探索幅度

在 `matlab_rl_optimizer.py` 的 `optimize()` 方法中修改：

```python
# 初始化梯度检测器
steep_detector = SteepGradientDetector(window_size=5, threshold=2.0)

for ep in range(max_ep):
    # ... 现有代码 ...
    
    # 检测梯度陡峭
    if steep_detector.is_steep_gradient():
        # 梯度陡峭：降低探索幅度，保守探索
        exploration_decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.5
        logger.info(f"  [Ep {ep+1}] 梯度陡峭检测，降低探索幅度 (decay={exploration_decay:.3f})")
    else:
        # 正常梯度：标准探索衰减
        exploration_decay = max(0.15, 1.0 - ep / float(max_ep))
    
    # 应用探索衰减
    if self._actor is not None and max_ep > 0:
        for i, k in enumerate(self._action_keys):
            _base_ls = 0.0 if k in self._PITCH_KEYS else -1.0
            self._actor.log_std[i] = float(
                np.clip(_base_ls + math.log(exploration_decay), -4.0, 2.0)
            )
    
    # ... 运行episode ...
    
    # 更新梯度检测器
    steep_detector.update(reward, new_params)
```

**预期效果**：
- ✅ 在梯度陡峭区域自动降低探索幅度
- ✅ 避免PPO大步长冲坏可行域
- ✅ 保持在可行域附近精细搜索

---

### 方案2：奖励崖式检测与回退 ⭐⭐⭐ 推荐

**思路**：检测奖励崖式下降，自动回退到上一个好的参数

#### 2.1 实现奖励崖式检测

```python
class RewardCliffDetector:
    def __init__(self, cliff_threshold=3.0, window_size=3):
        self.cliff_threshold = cliff_threshold  # 奖励下降倍数
        self.window_size = window_size
        self.reward_history = []
        self.param_history = []
    
    def detect_cliff(self):
        """检测是否掉入奖励崖"""
        if len(self.reward_history) < 2:
            return False, None
        
        recent = self.reward_history[-1]
        prev_best = max(self.reward_history[:-1])
        
        # 如果最近的奖励远低于之前的最好奖励，说明掉入了崖
        if prev_best > 0 and recent < prev_best / self.cliff_threshold:
            return True, self.param_history[self.reward_history.index(prev_best)]
        
        return False, None
    
    def update(self, reward, params):
        self.reward_history.append(reward)
        self.param_history.append(params.copy())
        if len(self.reward_history) > 20:
            self.reward_history.pop(0)
            self.param_history.pop(0)
```

#### 2.2 在RL循环中应用

```python
cliff_detector = RewardCliffDetector(cliff_threshold=2.0)

for ep in range(max_ep):
    # ... 采样action，运行simulation ...
    
    reward = self._compute_reward(metrics)
    
    # 检测奖励崖
    is_cliff, safe_params = cliff_detector.detect_cliff()
    
    if is_cliff and safe_params:
        logger.warning(
            f"  [Ep {ep+1}] ⚠️ 奖励崖检测！"
            f"从 {self._best_reward:.3f} 跌到 {reward:.3f}。"
            f"回退到安全参数。"
        )
        # 回退到安全参数，但加入小的扰动以继续探索
        new_params = safe_params.copy()
        for k in new_params:
            spec = ALL_TUNABLE_PARAM_SPECS[k]
            noise = np.random.normal(0, 0.02)  # 小的高斯噪声
            new_params[k] = np.clip(
                new_params[k] + noise * (spec["max"] - spec["min"]),
                spec["min"], spec["max"]
            )
        
        # 重新运行simulation
        metrics = await self._run_simulation_with_params(
            new_params, mission_conditions, script_path, n_mc
        )
        reward = self._compute_reward(metrics)
    
    cliff_detector.update(reward, new_params)
    
    # ... 继续正常的RL流程 ...
```

**预期效果**：
- ✅ 检测到掉入奖励崖时自动回退
- ✅ 避免RL被吸引到不可行区域
- ✅ 保持在可行域附近

---

### 方案3：约束采样 ⭐⭐

**思路**：在参数采样时加入约束，防止采样到已知的不可行区域

#### 3.1 记录不可行区域

```python
class InfeasibleRegionTracker:
    def __init__(self, param_specs):
        self.param_specs = param_specs
        self.infeasible_zones = []  # 记录不可行区域
        self.feasible_zones = []    # 记录可行区域
    
    def mark_infeasible(self, params, reason=""):
        """标记一个不可行的参数点"""
        self.infeasible_zones.append({
            "params": params.copy(),
            "reason": reason,
            "timestamp": time.time()
        })
    
    def mark_feasible(self, params):
        """标记一个可行的参数点"""
        self.feasible_zones.append({
            "params": params.copy(),
            "timestamp": time.time()
        })
    
    def is_near_infeasible(self, params, radius=0.1):
        """检查参数是否接近已知的不可行区域"""
        for zone in self.infeasible_zones[-10:]:  # 只检查最近10个
            distance = self._euclidean_distance(params, zone["params"])
            if distance < radius:
                return True, zone["reason"]
        return False, ""
    
    def _euclidean_distance(self, p1, p2):
        """计算参数空间中的欧氏距离（归一化）"""
        total = 0.0
        for k in p1:
            spec = self.param_specs[k]
            half = (spec["max"] - spec["min"]) / 2.0
            diff = (p1[k] - p2[k]) / half
            total += diff ** 2
        return math.sqrt(total)
```

#### 3.2 在采样时应用约束

```python
tracker = InfeasibleRegionTracker(ALL_TUNABLE_PARAM_SPECS)

for ep in range(max_ep):
    # ... 采样action ...
    
    new_params = self._action_to_params(action)
    
    # 检查是否接近不可行区域
    is_near_infeas, reason = tracker.is_near_infeasible(new_params, radius=0.15)
    
    if is_near_infeas:
        # 反向该action，避免进入不可行区域
        logger.debug(f"  [Ep {ep+1}] 接近不可行区域 ({reason})，反向探索")
        action = -action
        new_params = self._action_to_params(action)
    
    metrics = await self._run_simulation_with_params(
        new_params, mission_conditions, script_path, n_mc
    )
    
    reward = self._compute_reward(metrics)
    
    # 根据奖励标记可行/不可行
    if reward > -5.0:  # 阈值可调
        tracker.mark_feasible(new_params)
    else:
        tracker.mark_infeasible(new_params, reason=f"reward={reward:.3f}")
```

**预期效果**：
- ✅ 避免重复进入已知的不可行区域
- ✅ 引导探索向可行区域集中
- ✅ 提高探索效率

---

### 方案4：多尺度探索 ⭐⭐

**思路**：使用多个不同探索幅度的Actor，并根据效果动态选择

#### 4.1 多尺度Actor网络

```python
class MultiScaleActor:
    def __init__(self, state_dim, action_dim, hidden_dim, lr):
        # 三个不同探索幅度的Actor
        self.actor_conservative = ActorNet(state_dim, action_dim, hidden_dim, lr)  # 小步长
        self.actor_normal = ActorNet(state_dim, action_dim, hidden_dim, lr)        # 中步长
        self.actor_aggressive = ActorNet(state_dim, action_dim, hidden_dim, lr)    # 大步长
        
        self.success_count = {"conservative": 0, "normal": 0, "aggressive": 0}
        self.total_count = {"conservative": 0, "normal": 0, "aggressive": 0}
    
    def sample(self, state, explore=True):
        """根据历史成功率选择Actor"""
        # 计算每个Actor的成功率
        success_rates = {}
        for key in self.success_count:
            if self.total_count[key] > 0:
                success_rates[key] = self.success_count[key] / self.total_count[key]
            else:
                success_rates[key] = 0.5  # 初始值
        
        # 选择成功率最高的Actor（带一定的探索）
        if np.random.random() < 0.1:  # 10%概率随机选择
            actor_type = np.random.choice(["conservative", "normal", "aggressive"])
        else:
            actor_type = max(success_rates, key=success_rates.get)
        
        # 从选中的Actor采样
        if actor_type == "conservative":
            actor = self.actor_conservative
            scale = 0.5
        elif actor_type == "aggressive":
            actor = self.actor_aggressive
            scale = 1.5
        else:
            actor = self.actor_normal
            scale = 1.0
        
        action, lp = actor.sample(state, explore=explore)
        return action * scale, lp, actor_type
    
    def update_success(self, actor_type, success):
        """更新Actor的成功统计"""
        self.total_count[actor_type] += 1
        if success:
            self.success_count[actor_type] += 1
```

#### 4.2 在RL循环中应用

```python
multi_actor = MultiScaleActor(state_dim, action_dim, hidden_dim, lr_actor)

for ep in range(max_ep):
    state = self._build_state(...)
    action, lp, actor_type = multi_actor.sample(state, explore=True)
    
    new_params = self._action_to_params(action)
    metrics = await self._run_simulation_with_params(...)
    reward = self._compute_reward(metrics)
    
    # 判断是否成功（奖励改善）
    success = reward > self._best_reward
    multi_actor.update_success(actor_type, success)
    
    logger.info(f"  [Ep {ep+1}] Actor={actor_type} success={success} reward={reward:.3f}")
```

**预期效果**：
- ✅ 自动选择合适的探索幅度
- ✅ 在窄可行域中精细搜索
- ✅ 在宽可行域中大步长探索

---

## 方案对比

| 方案 | 难度 | 实施时间 | 效果 | 推荐度 |
|------|------|---------|------|--------|
| 方案1 | ⭐ | 1-2h | 很好 | ⭐⭐⭐ |
| 方案2 | ⭐ | 1-2h | 很好 | ⭐⭐⭐ |
| 方案3 | ⭐⭐ | 2-3h | 好 | ⭐⭐ |
| 方案4 | ⭐⭐⭐ | 3-4h | 优秀 | ⭐ |

---

## 推荐实施路径

### 快速解决（推荐）

```
1. 实施方案1（自适应探索衰减）
   └─ 时间：1-2小时
   └─ 效果：自动降低梯度陡峭区域的探索幅度
   
2. 如果还不够，添加方案2（奖励崖式检测）
   └─ 时间：额外1-2小时
   └─ 效果：检测到掉入奖励崖时自动回退
```

**总时间**：1-4小时  
**预期**：T4在50-100 episode内收敛

---

## 实施步骤

### 步骤1：添加梯度检测器

在 `matlab_rl_optimizer.py` 顶部添加：

```python
class SteepGradientDetector:
    # ... 上面的代码 ...
```

### 步骤2：修改optimize()方法

在 `optimize()` 方法的主循环中：

```python
# 初始化检测器
steep_detector = SteepGradientDetector(window_size=5, threshold=2.0)

for ep in range(max_ep):
    # ... 现有代码 ...
    
    # 检测梯度陡峭
    if steep_detector.is_steep_gradient():
        exploration_decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.5
        logger.info(f"  [Ep {ep+1}] 梯度陡峭，降低探索 (decay={exploration_decay:.3f})")
    else:
        exploration_decay = max(0.15, 1.0 - ep / float(max_ep))
    
    # 应用探索衰减
    if self._actor is not None and max_ep > 0:
        for i, k in enumerate(self._action_keys):
            _base_ls = 0.0 if k in self._PITCH_KEYS else -1.0
            self._actor.log_std[i] = float(
                np.clip(_base_ls + math.log(exploration_decay), -4.0, 2.0)
            )
    
    # ... 运行episode ...
    
    # 更新检测器
    steep_detector.update(reward, new_params)
```

### 步骤3：验证修改

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

预期日志输出：
```
[Ep 10] 梯度陡峭检测，降低探索幅度 (decay=0.075)
[Ep 15] 梯度陡峭检测，降低探索幅度 (decay=0.050)
[Ep 25] 梯度恢复正常，恢复标准探索 (decay=0.300)
```

---

## 预期结果

### 实施前
- T4工况：无法收敛（100 episode仍在振荡）
- 日志显示：奖励在-5到-2之间反复波动

### 实施后
- T4工况：50-100 episode内收敛
- 日志显示：梯度陡峭时自动降低探索，找到稳定的可行参数

---

## 总结

T4的窄可行域问题可以通过**RL探索策略的自适应调整**来解决：

1. **自适应探索衰减**：在梯度陡峭区域自动降低探索幅度
2. **奖励崖式检测**：检测到掉入奖励崖时自动回退
3. **约束采样**：避免重复进入已知的不可行区域
4. **多尺度探索**：自动选择合适的探索幅度

**推荐**：先实施方案1和2，这两个方案结合通常能解决T4的收敛问题。
