# Layer 3 优化逻辑 - 快速总结

## 核心逻辑

### 场景1：Layer 2 已满足

```
Layer 2 仿真结果：✅ 全部指标满足

Layer 3 处理：
  ├─ 直接使用 Layer 2 的仿真结果
  ├─ 不进行任何优化
  └─ 返回 status="done"

使用的仿真结果：Layer 2 的结果
```

### 场景2：Layer 2 未满足，Layer 3 进行优化

```
Layer 2 仿真结果：❌ 部分指标未满足

Layer 3 处理：
  ├─ 进行参数优化（Expert/PPO/CLS）
  ├─ 运行仿真获得优化结果
  └─ 返回 status="done" 或 "needs_iteration"

使用的仿真结果：优化后的结果
```

---

## 代码实现

### 路径 A：Layer 2 已满足（第184-196行）

```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics  # ← Layer 2 的结果
    
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,  # ← 使用 Layer 2 的结果
        "report_path": "",
    }
```

### 路径 B：Layer 3 进行优化（第246-248行）

```python
# Expert 优化
expert_result = await self._run_expert_tuning(...)
best_params  = expert_result.get("best_params", best_params)
best_metrics = expert_result.get("best_metrics", best_metrics)  # ← 优化结果

# PPO 优化
ppo_result = await self.rl_optimizer.optimize(...)
best_params  = ppo_result.get("best_params", best_params)
best_metrics = ppo_result.get("best_metrics", best_metrics)  # ← 优化结果
```

---

## 关键原则

✅ **使用最新的仿真结果**
- Layer 2 已满足 → 使用 Layer 2 的结果
- Layer 3 优化后 → 使用优化后的结果

✅ **避免重复仿真**
- 不在 Layer 3 重新运行 smoke test
- 直接使用已有的仿真结果

✅ **判断基于最新结果**
- 每个阶段的判断都基于该阶段的仿真结果
- 不混淆不同阶段的数据

---

## 相关文档

详见 `LAYER3_OPTIMIZATION_LOGIC.md`
