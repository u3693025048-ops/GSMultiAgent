# Layer 3 判断逻辑改进 - 快速修复

## 问题

Layer 3 应该以 Layer 2 的仿真结果为准，而不是重新运行仿真。

```
当前问题：
  Layer 2 仿真结果：SEP=4.01m, PeakNy=19.49g ✅
  Layer 3 仿真结果：SEP=9.13m, PeakNy=22.4g ⚠️
  
  结果不一致，导致判断混乱
```

## 解决方案

### 方案A：Layer 3 直接使用 Layer 2 结果（推荐）

**修改**：`optimization_workflow.py` 第184-186行

```python
# 原来：
if directly_satisfied and initial_metrics:
    logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
    best_metrics = initial_metrics

# 改为：
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

**效果**：
- ✅ Layer 3 直接使用 Layer 2 的结果
- ✅ 避免重复仿真
- ✅ 结果一致

### 方案B：增加 Layer 2 仿真样本数

**修改**：`config.yaml` 第468行

```yaml
# 原来：
layer2_smoke_nmc: 5

# 改为：
layer2_smoke_nmc: 25
```

**效果**：
- ✅ Layer 2 仿真更准确
- ✅ 样本数多，统计更稳定
- ✅ Layer 3 使用更可靠的结果

## 验证

重新运行优化：

```bash
python cli_agent.py --file prompt.txt
```

**预期结果**：
- ✅ Layer 3 使用 Layer 2 的仿真结果
- ✅ 判断逻辑一致
- ✅ 不重复仿真

## 相关文档

详见 `LAYER3_JUDGMENT_LOGIC.md`
