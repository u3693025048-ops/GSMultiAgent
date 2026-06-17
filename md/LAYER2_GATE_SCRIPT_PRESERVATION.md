# Layer 2 Gate 脚本保留机制

## 问题

当 `hermes_execution=false` 时，Layer 2 Gate 从 KB 模板重新生成脚本，而不是使用之前生成的脚本。

```
日志：
[run_simulation] No historical model found; falling back to KB template: monte_carlo_single.m
```

---

## 根本原因

```python
# cli_agent.py 第2037-2044行（改进前）
_gate_script = (
    hermes_generated_script  # ← 当 hermes_execution=false 时，这是空的
    or _find_latest_matlab_script(...)  # ← 找不到脚本
    or KB_TEMPLATE  # ← 回退到 KB 模板
)
```

当 Hermes 不执行时，`hermes_generated_script` 被重置为空，导致 Layer 2 Gate 无法找到脚本。

---

## 解决方案

### ✅ 已实施：脚本保留机制

**修改1**：`cli_agent.py` 第2037-2046行

```python
# 优先使用：当前轮生成的脚本 → 上一轮的脚本 → 最新脚本 → KB模板
_gate_script = (
    hermes_generated_script  # 当前轮 Hermes 生成的脚本
    or matlab_script_path  # ← 上一轮 Layer 3 使用的脚本
    or _find_latest_matlab_script(...)
    or KB_TEMPLATE
)
```

**修改2**：`cli_agent.py` 第2073-2080行

```python
if _g_ok:
    _gate_script = _g_script
    # 只在 Hermes 执行时更新 hermes_generated_script，保留脚本路径
    if wf_cfg.hermes_execution:
        hermes_generated_script = _g_script
    if _g_metrics:
        _gate_metrics = _g_metrics
        hermes_sim_metrics = _g_metrics
```

**修改3**：`cli_agent.py` 第2173-2176行

```python
# 保存本轮使用的脚本路径，供下一轮使用
if _wf_script and os.path.isfile(_wf_script):
    matlab_script_path = _wf_script
    logger.info(f"[Iteration {iteration}] Saved script path for next iteration: {os.path.basename(_wf_script)}")
```

---

## 工作流改进

### 改进前

```
第1轮迭代（Hermes 执行）
  ├─ Hermes 生成脚本 A：guidance_simulation_T4_MODIFY_LAW_1781107289.m
  ├─ hermes_generated_script = A
  └─ Layer 2 Gate 验证脚本 A ✅

第2轮迭代（hermes_execution=false）
  ├─ Hermes 不执行
  ├─ hermes_generated_script = ""（被重置）
  ├─ _find_latest_matlab_script() 找不到
  └─ Layer 2 Gate 从 KB 模板重新生成 ❌
```

### 改进后

```
第1轮迭代（Hermes 执行）
  ├─ Hermes 生成脚本 A：guidance_simulation_T4_MODIFY_LAW_1781107289.m
  ├─ hermes_generated_script = A
  ├─ Layer 2 Gate 验证脚本 A ✅
  └─ matlab_script_path = A（保存）

第2轮迭代（hermes_execution=false）
  ├─ Hermes 不执行
  ├─ hermes_generated_script = A（保留）
  ├─ _gate_script = A（优先使用）
  └─ Layer 2 Gate 验证脚本 A ✅
```

---

## 脚本选择优先级

```
优先级1：当前轮 Hermes 生成的脚本
  └─ hermes_generated_script（如果 Hermes 执行）

优先级2：上一轮 Layer 3 使用的脚本
  └─ matlab_script_path（如果 hermes_execution=false）

优先级3：最新生成的脚本
  └─ _find_latest_matlab_script()

优先级4：KB 模板
  └─ monte_carlo_single.m
```

---

## 关键改进

### 1. 脚本保留

```python
# 在循环结束时保存脚本路径
if _wf_script and os.path.isfile(_wf_script):
    matlab_script_path = _wf_script
```

**效果**：脚本不会丢失，可以在下一轮使用

### 2. 条件更新

```python
# 只在 Hermes 执行时更新
if wf_cfg.hermes_execution:
    hermes_generated_script = _g_script
```

**效果**：保留脚本路径，避免被覆盖

### 3. 优先级选择

```python
# 优先使用上一轮的脚本
_gate_script = (
    hermes_generated_script
    or matlab_script_path  # ← 新增
    or _find_latest_matlab_script(...)
    or KB_TEMPLATE
)
```

**效果**：避免不必要的重新生成

---

## 预期效果

| 场景 | 改进前 | 改进后 | 改进 |
|------|--------|--------|------|
| **第1轮（Hermes 执行）** | 生成脚本 A | 生成脚本 A | ✅ 相同 |
| **第2轮（hermes_execution=false）** | 从 KB 重新生成 ❌ | 使用脚本 A ✅ | ✅ 改进 |
| **脚本一致性** | ❌ 不一致 | ✅ 一致 | ✅ 改进 |
| **计算效率** | ❌ 重复生成 | ✅ 避免重复 | ✅ 改进 |

---

## 代码改进位置

| 文件 | 行号 | 改进 |
|------|------|------|
| `cli_agent.py` | 2037-2046 | 脚本选择逻辑 |
| `cli_agent.py` | 2073-2080 | 条件更新 |
| `cli_agent.py` | 2173-2176 | 脚本保留 |

---

## 总结

**问题**：
- hermes_execution=false 时，脚本被丢失
- Layer 2 Gate 从 KB 模板重新生成

**解决方案**：
1. 保留脚本路径（matlab_script_path）
2. 优先使用上一轮的脚本
3. 只在 Hermes 执行时更新 hermes_generated_script

**预期效果**：
- ✅ 脚本不会丢失
- ✅ 避免不必要的重新生成
- ✅ 保持脚本一致性
- ✅ 提高计算效率
