# Layer 3 判断逻辑改进 - 使用 Layer 2 仿真结果

## 问题描述

当前 Layer 3 的判断逻辑：
- Layer 3 运行自己的仿真（通常 nmc=5 smoke test）
- 基于 Layer 3 的仿真结果进行判断
- 导致与 Layer 2 的仿真结果不一致

**用户建议**：
- Layer 3 应该以 Layer 2 的仿真结果为准
- 不应该重新运行仿真，而是使用 Layer 2 的结果

---

## 当前流程

```
Layer 2 Gate 验证
  ├─ 运行仿真（nmc=5 smoke test）
  ├─ 获得仿真结果：SEP=4.01m, PeakNy=19.49g
  └─ 判断：✅ 通过 → 进入 Layer 3

Layer 3 RL 优化
  ├─ 重新运行仿真（nmc=5 smoke test）
  ├─ 获得仿真结果：SEP=9.13m, PeakNy=22.4g ❌ 不同！
  └─ 判断：❌ 未通过 → 需要继续优化
```

**问题**：
- Layer 3 重新运行了仿真
- 结果与 Layer 2 不一致
- 导致判断结果不一致

---

## 改进方案

### 方案1：Layer 3 使用 Layer 2 的仿真结果（推荐）

```
Layer 2 Gate 验证
  ├─ 运行仿真（nmc=5 smoke test）
  ├─ 获得仿真结果：SEP=4.01m, PeakNy=19.49g
  └─ 保存结果供 Layer 3 使用

Layer 3 RL 优化
  ├─ 读取 Layer 2 的仿真结果
  ├─ 使用 Layer 2 的结果进行判断
  └─ 判断：✅ 通过 → 完成优化
```

**优点**：
- ✅ 避免重复仿真
- ✅ 结果一致
- ✅ 判断逻辑清晰

**实现**：
```python
# optimization_workflow.py
if directly_satisfied and initial_metrics:
    # 使用 Layer 2 的仿真结果
    best_metrics = initial_metrics  # ← Layer 2 的结果
    
    # 直接返回，不重新仿真
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,
        "report_path": "",
    }
```

---

### 方案2：Layer 3 运行完整仿真（nmc=25）

```
Layer 2 Gate 验证
  ├─ 运行 smoke test（nmc=5）
  ├─ 获得结果：SEP=9.13m, PeakNy=22.4g
  └─ 判断：⚠️ 接近边界

Layer 3 RL 优化
  ├─ 运行完整仿真（nmc=25）
  ├─ 获得结果：SEP=4.01m, PeakNy=19.49g ✅
  └─ 判断：✅ 通过 → 完成优化
```

**优点**：
- ✅ 更准确的仿真结果
- ✅ 样本数多，统计更稳定

**缺点**：
- ❌ 计算时间长
- ❌ 资源消耗大

---

### 方案3：统一使用相同的 nmc（推荐）

```
Layer 2 Gate 验证
  ├─ 运行仿真（nmc=25）
  └─ 获得结果：SEP=4.01m, PeakNy=19.49g

Layer 3 RL 优化
  ├─ 使用 Layer 2 的结果
  └─ 判断：✅ 通过
```

**优点**：
- ✅ 结果一致
- ✅ 判断逻辑清晰
- ✅ 避免重复仿真

---

## 代码改进位置

### 位置1：`optimization_workflow.py` 第184-186行

**当前代码**：
```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics
```

**改进**：
```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    logger.info(f"[OptimWorkflow] Using Layer 2 metrics: {initial_metrics}")
    best_metrics = initial_metrics
    
    # 直接返回，不继续后续处理
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,
        "report_path": "",
    }
```

### 位置2：`layer2_script_gate.py`

**确保 Layer 2 保存仿真结果**：
```python
# 保存 Layer 2 的仿真结果供 Layer 3 使用
layer2_metrics = {
    "hit_rate": hit_rate,
    "SEP": sep,
    "peak_ny": peak_ny,
    "PM": pm,
    "BW": bw,
}

# 传递给 Layer 3
return {
    "passed": passed,
    "metrics": layer2_metrics,
}
```

### 位置3：`judgment_agent.py`

**改进判断逻辑**：
```python
def judge_requirements(self, metrics, task_prompt):
    """
    Judge if requirements are met.
    
    Should use the metrics from Layer 2, not re-run simulation.
    """
    # 使用传入的 metrics（来自 Layer 2）
    # 不应该重新运行仿真
    
    hit_rate = metrics.get("hit_rate", 0)
    sep = metrics.get("SEP", 99)
    peak_ny = metrics.get("peak_ny", 99)
    pm = metrics.get("PM", 0)
    bw = metrics.get("BW", 0)
    
    # 判断逻辑
    ...
```

---

## 配置改进

### 修改 `config.yaml`

```yaml
simulation:
  # Layer 2 Gate 仿真配置
  layer2_smoke_nmc: 25  # ← 增加样本数，提高准确性
  
  # Layer 3 RL 优化配置
  # 不应该重新运行 smoke test
  # 应该直接使用 Layer 2 的结果
  layer3_use_layer2_metrics: true  # ← 新增配置
```

---

## 工作流改进

### 改进前

```
Layer 2 Gate
  ├─ 运行仿真（nmc=5）
  └─ 判断：通过/失败

Layer 3 RL 优化
  ├─ 重新运行仿真（nmc=5）❌ 重复
  └─ 判断：通过/失败
```

### 改进后

```
Layer 2 Gate
  ├─ 运行仿真（nmc=25）
  ├─ 保存结果
  └─ 判断：通过/失败

Layer 3 RL 优化
  ├─ 读取 Layer 2 结果
  ├─ 使用 Layer 2 的判断
  └─ 如果通过，直接完成
     如果失败，进行参数优化
```

---

## 快速修复

### 步骤1：改进 `optimization_workflow.py`

在第184-186行后添加早期返回：

```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics
    
    # 直接返回，不继续后续处理
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,
        "report_path": "",
    }
```

### 步骤2：增加 Layer 2 仿真样本数

在 `config.yaml` 中：

```yaml
simulation:
  layer2_smoke_nmc: 25  # ← 从 5 改为 25
```

### 步骤3：改进判断逻辑

确保 Layer 3 的判断基于 Layer 2 的结果，而不是重新仿真。

---

## 预期效果

| 方面 | 改进前 | 改进后 | 改进 |
|------|--------|--------|------|
| **结果一致性** | ❌ 不一致 | ✅ 一致 | ✅ |
| **计算效率** | ❌ 重复仿真 | ✅ 避免重复 | ✅ |
| **判断逻辑** | ❌ 混乱 | ✅ 清晰 | ✅ |
| **准确性** | ⚠️ 样本少 | ✅ 样本多 | ✅ |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `optimization_workflow.py` | 184-186 | directly_satisfied 逻辑 |
| `layer2_script_gate.py` | — | Layer 2 仿真结果保存 |
| `judgment_agent.py` | — | 判断逻辑 |
| `config.yaml` | simulation | 仿真配置 |

---

## 总结

**问题**：
- Layer 3 重新运行仿真，导致结果与 Layer 2 不一致
- 判断逻辑混乱

**用户建议**：
- Layer 3 应该以 Layer 2 的仿真结果为准
- 不应该重新运行仿真

**解决方案**：
1. Layer 3 直接使用 Layer 2 的仿真结果
2. 增加 Layer 2 的仿真样本数（nmc=25）
3. 改进判断逻辑，避免重复仿真

**预期效果**：
- ✅ 结果一致
- ✅ 计算效率高
- ✅ 判断逻辑清晰
