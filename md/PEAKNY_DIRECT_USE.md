# PeakNy 参数直接使用说明

## 问题回顾

之前考虑在Layer 2中强制复制`peak_ny`为`peak_ny_max`。但这是**不必要的**。

## 原因分析

### 仿真已经返回peak_ny_max

在`matlab_rl_optimizer.py`的`parse_sim_stdout()`函数中：

```python
# 第502-503行：从MATLAB输出提取max=XXg
ny_max_vals: List[float] = []
for m in re.finditer(r"max=(\d+(?:\.\d+)?)\s*g", raw, re.IGNORECASE):
    ny_max_vals.append(float(m.group(1)))

# 第616-618行：聚合到metrics中
if ny_max_vals:
    defaults["peak_ny_max"] = max(ny_max_vals)
    defaults["peak_n_max"] = defaults["peak_ny_max"]
```

**仿真解析器已经从MATLAB输出中提取了`max=XXg`的值**，并存储为`peak_ny_max`。

### 完整的metrics结构

仿真返回的metrics包含：

```python
metrics = {
    "hit_rate": 100.0,
    "SEP": 4.66,
    "peak_ny": 17.23,      # 平均值
    "peak_ny_max": 27.37,  # 最大值 ← 已由仿真提供
    "pitch_PM": 51.4,
    "pitch_BW": 80.04,
}
```

## 解决方案

**不需要在Layer 2中强制复制**。直接使用仿真返回的`peak_ny_max`。

### _rule_check中的处理

在`_rule_check`函数中，已经正确处理了`peak_ny_max`：

```python
if "peak_ny_max" in reqs:
    # Use MAXIMUM PeakNy value (most strict)
    pny_avg = metrics.get("peak_ny", 0.0)
    pny_max = metrics.get("peak_ny_max", 0.0)  # ← 直接获取仿真提供的值
    
    if pny_max > 0.0:
        ok = pny_max <= reqs["peak_ny_max"]
        satisfied = satisfied and ok
```

## 数据流

```
MATLAB仿真输出
    ↓
parse_sim_stdout() 提取 max=XXg
    ↓
返回 metrics = {..., "peak_ny_max": 27.37, ...}
    ↓
Layer 2 judge_requirements_tool 接收 metrics
    ↓
_rule_check() 直接使用 metrics["peak_ny_max"]
    ↓
进行最大值检查（方案B）
```

## 为什么不需要强制复制

1. **仿真已经提供** - `parse_sim_stdout()`已经从MATLAB输出中提取了`max=XXg`
2. **数据完整** - metrics中总是包含`peak_ny_max`
3. **无需fallback** - 不存在"只有peak_ny而没有peak_ny_max"的情况
4. **简洁清晰** - 直接使用仿真提供的值，逻辑更清楚

## 修改清单

- ✅ 撤销Layer 2中的强制复制逻辑
- ✅ 直接使用仿真返回的`peak_ny_max`
- ✅ 保持_rule_check中的方案B逻辑不变

## 总结

**关键认识**：
- 仿真解析器已经完整地提取了`peak_ny_max`
- Layer 2无需做任何转换，直接使用即可
- 方案B（最大值检查）可以正常工作

这样的设计更加**简洁、清晰、可维护**。
