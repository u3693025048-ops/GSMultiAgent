# Layer 2 Gate 脚本选择问题诊断

## 问题描述

当 `hermes_execution=false` 时，Layer 2 Gate 仍然从 KB 模板重新生成脚本，而不是使用之前生成的脚本。

```
日志：
[Layer 2 Gate] ✗ BLOCKED Layer 3 — MODIFY 闭环快扫 PeakNy_max=48.8g>25g，拒绝进入 Layer3
[run_simulation] No historical model found; falling back to KB template: monte_carlo_single.m
```

---

## 根本原因

### 当前流程

```python
# cli_agent.py 第2037-2041行
_gate_script = (
    hermes_generated_script  # ← 当 hermes_execution=false 时，这是空的
    or _find_latest_matlab_script(...)  # ← 找不到脚本
)

# Layer 2 Gate 中
if need_regen:
    logger.info("[Layer2Gate] Regenerating from KB template (reason=%s)", rl_reason)
    # 从 KB 模板重新生成脚本
```

### 问题分析

```
1. 第一次迭代（Hermes 执行）
   ├─ Hermes 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m
   └─ hermes_generated_script = "guidance_simulation_T4_MODIFY_LAW_1781107289.m"

2. 进入 Layer 2 Gate
   ├─ _gate_script = hermes_generated_script（有值）
   └─ Layer 2 Gate 验证脚本

3. 第二次迭代（hermes_execution=false）
   ├─ Hermes 不执行（hermes_execution=false）
   ├─ hermes_generated_script = ""（被重置）
   ├─ _find_latest_matlab_script() 找不到脚本
   ├─ _gate_script = ""（空）
   └─ Layer 2 Gate 从 KB 模板重新生成 ❌
```

---

## 解决方案

### 方案1：保留上一轮生成的脚本路径

**修改**：`cli_agent.py` 第2037-2041行

```python
# 原来：
_gate_script = (
    hermes_generated_script
    or _find_latest_matlab_script(
        str(MATLAB_SCRIPTS_DIR), str(MODEL_OUTPUT_DIR), "."
    )
)

# 改为：
_gate_script = (
    hermes_generated_script  # 当前轮生成的脚本
    or _wf_script  # ← 上一轮的脚本（如果有）
    or _find_latest_matlab_script(
        str(MATLAB_SCRIPTS_DIR), str(MODEL_OUTPUT_DIR), "."
    )
)
```

**效果**：
- ✅ 第一次迭代：使用 Hermes 生成的脚本
- ✅ 后续迭代：使用上一轮的脚本（如果 hermes_execution=false）
- ✅ 避免不必要的重新生成

### 方案2：在 Layer 2 Gate 中保留脚本

**修改**：`cli_agent.py` 第2071-2076行

```python
# 原来：
if _g_ok:
    _gate_script = _g_script
    hermes_generated_script = _g_script
    if _g_metrics:
        _gate_metrics = _g_metrics
        hermes_sim_metrics = _g_metrics

# 改为：
if _g_ok:
    _gate_script = _g_script
    # 只在 Hermes 执行时更新 hermes_generated_script
    if wf_cfg.hermes_execution:
        hermes_generated_script = _g_script
    if _g_metrics:
        _gate_metrics = _g_metrics
        hermes_sim_metrics = _g_metrics
```

**效果**：
- ✅ 保留 hermes_generated_script 的值
- ✅ 下一轮迭代时可以继续使用
- ✅ 避免脚本丢失

---

## 推荐方案

### 综合方案：保留脚本 + 优先使用上一轮

**步骤1**：修改 Layer 2 Gate 脚本选择逻辑

```python
# cli_agent.py 第2037-2041行
_gate_script = (
    hermes_generated_script  # 当前轮生成的脚本
    or _wf_script  # 上一轮的脚本
    or _find_latest_matlab_script(...)
)
```

**步骤2**：修改 hermes_generated_script 更新逻辑

```python
# cli_agent.py 第2071-2076行
if _g_ok:
    _gate_script = _g_script
    # 只在 Hermes 执行时更新
    if wf_cfg.hermes_execution:
        hermes_generated_script = _g_script
    if _g_metrics:
        _gate_metrics = _g_metrics
        hermes_sim_metrics = _g_metrics
```

**效果**：
- ✅ 脚本不会丢失
- ✅ 优先使用最新生成的脚本
- ✅ 回退到上一轮脚本
- ✅ 最后回退到 KB 模板

---

## 工作流对比

### 改进前

```
第1轮迭代（Hermes 执行）
  ├─ Hermes 生成脚本 A
  ├─ hermes_generated_script = A
  └─ Layer 2 Gate 验证脚本 A

第2轮迭代（hermes_execution=false）
  ├─ Hermes 不执行
  ├─ hermes_generated_script = ""（被重置）
  ├─ _find_latest_matlab_script() 找不到
  └─ Layer 2 Gate 从 KB 模板重新生成 ❌
```

### 改进后

```
第1轮迭代（Hermes 执行）
  ├─ Hermes 生成脚本 A
  ├─ hermes_generated_script = A
  └─ Layer 2 Gate 验证脚本 A

第2轮迭代（hermes_execution=false）
  ├─ Hermes 不执行
  ├─ hermes_generated_script = A（保留）
  ├─ _gate_script = A（优先使用）
  └─ Layer 2 Gate 验证脚本 A ✅
```

---

## 代码改进位置

| 文件 | 行号 | 改进 |
|------|------|------|
| `cli_agent.py` | 2037-2041 | 脚本选择逻辑 |
| `cli_agent.py` | 2071-2076 | hermes_generated_script 更新 |

---

## 总结

**问题**：
- hermes_execution=false 时，脚本被丢失
- Layer 2 Gate 从 KB 模板重新生成

**原因**：
- hermes_generated_script 被重置为空
- _find_latest_matlab_script() 找不到脚本

**解决方案**：
1. 保留 hermes_generated_script 的值
2. 优先使用上一轮的脚本
3. 回退到 KB 模板

**预期效果**：
- ✅ 脚本不会丢失
- ✅ 避免不必要的重新生成
- ✅ 保持脚本一致性
