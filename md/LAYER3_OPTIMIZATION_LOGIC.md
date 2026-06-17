# Layer 3 优化逻辑说明

## 完整的判断流程

### 场景1：Layer 2 已满足（directly_satisfied=True）

```
Layer 2 Gate 验证
  ├─ 运行仿真（nmc=25）
  ├─ 获得仿真结果：SEP=4.01m, PeakNy=19.49g
  └─ 判断：✅ 全部指标满足

Layer 3 RL 优化
  ├─ 接收 directly_satisfied=True
  ├─ 直接使用 Layer 2 的仿真结果
  └─ 返回 status="done"
     ├─ best_metrics = Layer 2 的结果
     └─ 不进行任何优化
```

**代码**（第184-196行）：
```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics  # ← 使用 Layer 2 的结果
    
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,  # ← Layer 2 的仿真结果
        "report_path": "",
    }
```

---

### 场景2：Layer 2 未满足，Layer 3 进行优化

```
Layer 2 Gate 验证
  ├─ 运行仿真（nmc=25）
  ├─ 获得仿真结果：SEP=9.13m, PeakNy=22.4g
  └─ 判断：❌ 部分指标未满足

Layer 3 RL 优化
  ├─ 接收 directly_satisfied=False
  ├─ 进行参数优化（Expert/PPO）
  ├─ 获得优化后的参数
  ├─ 运行仿真获得优化结果
  └─ 返回 status="done" 或 "needs_iteration"
     ├─ best_metrics = 优化后的仿真结果 ✅
     └─ best_params = 优化后的参数
```

**代码**（第246-248行）：
```python
# Expert 优化
expert_result = await self._run_expert_tuning(...)
best_params  = expert_result.get("best_params", best_params)
best_metrics = expert_result.get("best_metrics", best_metrics)  # ← 优化后的结果
rl_result    = expert_result

# PPO 优化
ppo_result = await self.rl_optimizer.optimize(...)
best_params  = ppo_result.get("best_params", best_params)
best_metrics = ppo_result.get("best_metrics", best_metrics)  # ← 优化后的结果
rl_result = ppo_result
```

---

## 完整的工作流

```
┌─────────────────────────────────────────────────────────┐
│ Layer 2 Gate 验证                                        │
│  ├─ 运行仿真（nmc=25）                                  │
│  └─ 判断：满足 or 未满足                                │
└─────────────────────────────────────────────────────────┘
                          ↓
         ┌────────────────┴────────────────┐
         ↓                                  ↓
    ✅ 满足                            ❌ 未满足
         ↓                                  ↓
┌─────────────────────────┐    ┌──────────────────────────┐
│ Layer 3 - 路径 A        │    │ Layer 3 - 路径 B         │
│ 直接使用 Layer 2 结果   │    │ 进行参数优化             │
│                         │    │                          │
│ 1. 读取 Layer 2 结果    │    │ 1. 选择优化策略          │
│ 2. 不进行任何优化       │    │    (Expert/PPO/CLS)      │
│ 3. 返回 status="done"   │    │ 2. 运行优化              │
│                         │    │ 3. 获得优化参数          │
│ best_metrics = Layer2   │    │ 4. 运行仿真              │
│ best_params = 初始参数  │    │ 5. 获得优化结果          │
└─────────────────────────┘    │                          │
                               │ best_metrics = 优化结果  │
                               │ best_params = 优化参数   │
                               └──────────────────────────┘
                                          ↓
                               ┌──────────────────────────┐
                               │ 判断优化是否满足         │
                               │                          │
                               │ ✅ 满足 → status="done"  │
                               │ ❌ 未满足 → 继续优化     │
                               └──────────────────────────┘
```

---

## 关键点

### 1. Layer 2 的仿真结果是基准

```python
# Layer 2 运行仿真（nmc=25）
layer2_metrics = run_simulation(script, nmc=25)

# Layer 3 直接使用 Layer 2 的结果（如果满足）
if directly_satisfied:
    best_metrics = layer2_metrics  # ← 使用 Layer 2 的结果
```

### 2. Layer 3 优化后使用优化结果

```python
# Layer 3 进行优化
optimization_result = await rl_optimizer.optimize(...)

# 使用优化后的结果
best_metrics = optimization_result.get("best_metrics")  # ← 优化后的结果
best_params = optimization_result.get("best_params")
```

### 3. 避免重复仿真

```python
# ❌ 错误：重新运行仿真
if directly_satisfied:
    best_metrics = run_simulation(script, nmc=5)  # ← 重复！

# ✅ 正确：直接使用 Layer 2 的结果
if directly_satisfied:
    best_metrics = initial_metrics  # ← Layer 2 的结果
```

---

## 代码位置

| 场景 | 文件 | 行号 | 说明 |
|------|------|------|------|
| **Layer 2 已满足** | `optimization_workflow.py` | 184-196 | 直接使用 Layer 2 结果 |
| **Expert 优化** | `optimization_workflow.py` | 236-248 | 使用 Expert 优化结果 |
| **PPO 优化** | `optimization_workflow.py` | 273-300 | 使用 PPO 优化结果 |
| **CLS 优化** | `optimization_workflow.py` | 311-343 | 使用 CLS 优化结果 |

---

## 总结

**Layer 3 的判断逻辑**：

1. **如果 Layer 2 已满足**（directly_satisfied=True）
   - ✅ 直接使用 Layer 2 的仿真结果
   - ✅ 不进行任何优化
   - ✅ 返回 status="done"

2. **如果 Layer 2 未满足**（directly_satisfied=False）
   - ✅ 进行参数优化（Expert/PPO/CLS）
   - ✅ 使用优化后的仿真结果
   - ✅ 根据优化结果判断是否满足

**关键原则**：
- ✅ 使用最新的仿真结果进行判断
- ✅ 避免重复仿真
- ✅ 优化后使用优化结果
