# Judge Requirements 判定逻辑说明

## 问题

BW（带宽）=98.6 r/s 超过了 85 的上限，但 `judge_requirements` 仍然判定 `satisfied=true`。

```
规则检查结果：
  - 命中率：96.0% ✓ [OK]
  - SEP：0.0m ✓ [OK]
  - PeakNy：22.52g ✓ [OK]
  - PM：67.2° ✓ [OK]
  - BW：98.6 r/s ✗ [NG]  ← 超过 85 上限

判定结果：satisfied = true ❓
```

---

## 根本原因

### 两阶段判定逻辑

```python
# 阶段1：规则检查
satisfied, reasons = _rule_check(m, reqs)
# 结果：satisfied = False（因为 BW 超限）

# 阶段2：LLM 判定（反思智能体）
if self._reflection_agent is not None:
    ref = await self._reflection_agent.reflect(task_prompt, {"metrics": m})
    llm_satisfied = not ref.get("needs_optimization", True)
    
    # 关键：LLM 可以覆盖规则检查
    if llm_satisfied and not satisfied:
        if _hard_constraint_failed(reasons):
            # 硬约束失败 → 不放行
            pass
        else:
            # 软约束失败 → LLM 可以放行
            satisfied = True  # ← 这里被设置为 True
```

### 硬约束 vs 软约束

```python
def _hard_constraint_failed(reasons: list) -> bool:
    """True when rule check failed on safety-critical metrics (never LLM-overridden)."""
    for r in reasons:
        if "[NG]" not in r:
            continue
        # 硬约束：安全关键指标
        if any(k in r for k in ("PeakNy", "命中率", "SEP", "hit_rate")):
            return True  # ← 硬约束失败，不允许 LLM 覆盖
    return False  # ← 只有软约束失败，允许 LLM 覆盖
```

### 你的情况

```
规则检查：
  - PeakNy：22.52g ✓ [OK]  ← 硬约束通过
  - 命中率：96.0% ✓ [OK]   ← 硬约束通过
  - SEP：0.0m ✓ [OK]       ← 硬约束通过
  - BW：98.6 r/s ✗ [NG]    ← 软约束失败

_hard_constraint_failed() 检查：
  - 只检查 PeakNy/命中率/SEP
  - BW 不在检查列表中
  - 返回 False（没有硬约束失败）

LLM 判定：
  - llm_satisfied = True
  - 硬约束未失败 → 允许 LLM 放行
  - satisfied = True ✓
```

---

## 约束分类

### 硬约束（Critical - Never LLM-Overridden）

```
这些指标不允许 LLM 覆盖，必须严格满足：

1. PeakNy（峰值过载）
   - 过高会导致结构损伤
   - 必须严格控制

2. 命中率（hit_rate）
   - 任务成功的基本指标
   - 过低表示任务失败

3. SEP（脱靶量）
   - 命中精度
   - 过大表示任务失败

4. PM（相位裕度）✅ 硬约束
   - 稳定性指标
   - 必须在规定范围内

5. BW（带宽）✅ 硬约束
   - 响应速度指标
   - 必须在规定范围内
```

---

## 工作流

### 规则检查（第一阶段）

```python
def _rule_check(metrics, reqs):
    satisfied = True
    reasons = []
    
    # 检查每个指标
    for metric_name, metric_value in metrics.items():
        ok = metric_value 满足要求
        satisfied = satisfied and ok
        reasons.append(f"{metric_name} {metric_value} {'[OK]' if ok else '[NG]'}")
    
    return satisfied, reasons
```

**结果**：
- 如果所有指标都满足 → `satisfied = True`
- 如果任何指标不满足 → `satisfied = False`

### LLM 判定（第二阶段）

```python
if llm_satisfied and not satisfied:
    # LLM 认为满足，但规则检查不满足
    
    if _hard_constraint_failed(reasons):
        # 硬约束失败 → 不允许 LLM 覆盖
        satisfied = False
    else:
        # 只有软约束失败 → 允许 LLM 覆盖
        satisfied = True
```

**逻辑**：
- 硬约束失败 → 强制 `satisfied = False`
- 只有软约束失败 → 允许 `satisfied = True`

---

## 为什么这样设计？

### 安全考虑

```
硬约束（安全关键）：
  - PeakNy 过高 → 飞行器结构损伤 → 必须严格控制
  - 命中率过低 → 任务失败 → 必须严格控制
  - SEP 过大 → 命中精度差 → 必须严格控制

软约束（性能相关）：
  - PM 略低 → 稳定性略差，但仍可接受
  - BW 略高 → 响应速度略快，可能是优势
  - LLM 可以综合考虑，做出工程判断
```

### 灵活性

```
LLM 可以考虑：
  - 整体性能是否满足任务需求
  - 各指标之间的权衡
  - 工程可行性
  - 成本效益

例如：
  - BW 略超 → 但命中率 96%，SEP 0m，PeakNy 22.5g
  - 整体来看，任务已经很好地完成了
  - LLM 可以判定为 satisfied = true
```

---

## 已实施的改进

### ✅ PM 和 BW 均为硬约束

```python
def _hard_constraint_failed(reasons: list) -> bool:
    """True when rule check failed on safety-critical metrics (never LLM-overridden)."""
    for r in reasons:
        if "[NG]" not in r:
            continue
        # Hard constraints: PeakNy, hit_rate, SEP, PM, BW (all critical)
        if any(k in r for k in ("PeakNy", "命中率", "SEP", "hit_rate", "PM", "BW")):
            return True
    return False
```

**效果**：
- PM 超限 → 强制 `satisfied = False`
- BW 超限 → 强制 `satisfied = False`
- 需要继续 RL 优化
- LLM 无法覆盖这些约束

---

## 总结

**问题**：
- BW 超限（98.6 > 85）
- 但 `satisfied = true`

**原因**：
- BW 原来是软约束
- LLM 可以覆盖软约束失败

**解决方案**：
- ✅ 将 PM 和 BW 改为**硬约束**
- 修改 `_hard_constraint_failed()` 函数
- 添加 "PM" 和 "BW" 到硬约束检查列表

**新的判定逻辑**：
```
硬约束失败？（PeakNy/命中率/SEP/PM/BW）
  ├─ 是 → satisfied = False（不允许 LLM 覆盖）
  └─ 否 → LLM 决定（允许 LLM 覆盖）
```

**预期效果**：
- ✅ PM 超限 → 强制 satisfied = False
- ✅ BW 超限 → 强制 satisfied = False
- ✅ 需要继续 RL 优化
- ✅ LLM 无法覆盖这些约束
