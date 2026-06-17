# directly_satisfied=True 仍继续迭代 - 快速修复

## 问题

```
[Layer 3] Optimization Workflow | script=guidance_simulation_1781106089.m
directly_satisfied=True  为什么指标满足了，仍然在迭代
```

## 原因

**外层迭代配置**：`config.yaml` 中 `workflow.max_iterations: 4`

```yaml
workflow:
  max_iterations: 4  # ← 设置为4轮迭代
```

**工作流逻辑**：
- 即使 Layer 3 返回 `status="done"`
- 外层循环仍会继续迭代，直到达到 `max_iterations` 轮数

```
迭代流程：
  第1轮：directly_satisfied=True → status="done" ✅
  第2轮：继续迭代 ❌
  第3轮：继续迭代 ❌
  第4轮：继续迭代 ❌
  完成：达到 max_iterations=4
```

## 解决方案

### ✅ 快速修复：减少迭代轮数

**修改**：`config.yaml` 第148行

```yaml
# 原来：
workflow:
  max_iterations: 4

# 改为：
workflow:
  max_iterations: 1
```

**理由**：
- 指标已满足，无需继续迭代
- 减少不必要的计算时间
- 节省资源

**效果**：
- ✅ 满足时立即停止
- ✅ 减少计算时间
- ✅ 提高效率

## 验证

重新运行优化：

```bash
python cli_agent.py --file prompt.txt
```

**预期结果**：
- ✅ 第1轮：directly_satisfied=True → status="done"
- ✅ 立即完成，不继续迭代
- ✅ 生成最终报告

## 相关配置

### 迭代轮数说明

```yaml
workflow:
  max_iterations: N  # N 轮迭代
```

| 值 | 说明 | 用途 |
|-----|------|------|
| **1** | 单轮 | 指标已满足，快速完成 |
| **2-3** | 少轮 | 指标接近满足，需要微调 |
| **4-5** | 多轮 | 指标相差较大，需要多次迭代 |

## 后续改进（可选）

### 改进工作流逻辑

在 `optimization_workflow.py` 中添加早期退出：

```python
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics
    # 直接返回，不继续后续步骤
    return {
        "status": "done",
        "best_params": initial_auto_params or {},
        "best_metrics": best_metrics,
        "report_path": "",
    }
```

## 相关文档

详见 `DIRECTLY_SATISFIED_ITERATION_ANALYSIS.md`
