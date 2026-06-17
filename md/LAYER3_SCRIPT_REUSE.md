# Layer 3 应该使用 Layer 2 生成的脚本

## 问题描述

当前的工作流：

```
Layer 2 Gate 验证
  ├─ 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m
  ├─ 运行仿真（nmc=25）
  └─ 判断：✅ 满足 or ❌ 未满足

Layer 3 RL 优化
  ├─ 重新生成脚本：guidance_simulation_T4_modlaw_1781109633.m ❌ 不同的脚本！
  ├─ 运行仿真（nmc=5）
  └─ 判断：结果与 Layer 2 不一致
```

**问题**：
- Layer 3 重新生成了脚本
- 导致脚本版本不同
- 导致仿真结果不同
- 导致判断结果不一致

---

## 改进方案

### 推荐方案：Layer 3 直接使用 Layer 2 的脚本

```
Layer 2 Gate 验证
  ├─ 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m ✅
  ├─ 运行仿真（nmc=25）
  └─ 判断：✅ 满足 or ❌ 未满足

Layer 3 RL 优化
  ├─ 使用 Layer 2 的脚本 ✅ 相同的脚本
  ├─ 运行仿真（nmc=25）
  └─ 判断：结果与 Layer 2 一致 ✅
```

**优点**：
- ✅ 脚本版本一致
- ✅ 仿真结果一致
- ✅ 判断逻辑清晰
- ✅ 避免重复生成

---

## 实现方案

### 方案1：禁用 Layer 3 的脚本生成

**修改**：`config.yaml`

```yaml
workflow:
  hermes_execution: false  # ← Layer 3 不执行 Hermes 生成
```

**效果**：
- ✅ Layer 3 直接使用 Layer 2 的脚本
- ✅ 避免重复生成
- ✅ 结果一致

**缺点**：
- ❌ Layer 3 无法修改脚本
- ❌ 如果 Layer 2 的脚本有问题，无法修复

### 方案2：Layer 3 有条件地使用 Layer 2 脚本

**逻辑**：
```python
# Layer 3 工作流
if directly_satisfied and initial_metrics:
    # Layer 2 已满足，直接使用 Layer 2 的脚本
    script_path = layer2_script_path  # ← 使用 Layer 2 的脚本
    hermes_execution = False  # ← 不重新生成
else:
    # Layer 2 未满足，可以选择：
    # 方案A：使用 Layer 2 的脚本进行参数优化
    script_path = layer2_script_path
    hermes_execution = False
    
    # 方案B：重新生成脚本（仅在必要时）
    # script_path = hermes_generated_script
    # hermes_execution = True
```

**效果**：
- ✅ Layer 2 满足时使用 Layer 2 脚本
- ✅ Layer 2 未满足时也使用 Layer 2 脚本（进行参数优化）
- ✅ 避免不必要的脚本重生成

---

## 代码改进位置

### 位置1：`cli_agent.py` 中的 Layer 3 调用

**当前代码**：
```python
# Layer 3 会根据 hermes_execution 配置重新生成脚本
if hermes and hermes_available and wf_cfg.hermes_execution:
    # Hermes 重新生成脚本
    hermes_response = await hermes.run_with_tools(...)
    hermes_generated_script = _capture_script_path()
```

**改进**：
```python
# Layer 3 应该使用 Layer 2 的脚本
if directly_satisfied:
    # Layer 2 已满足，禁用 Hermes 生成
    hermes_execution = False
    script_path = hermes_generated_script  # ← Layer 2 的脚本
else:
    # Layer 2 未满足，可以选择是否重新生成
    # 推荐：也使用 Layer 2 的脚本，进行参数优化
    hermes_execution = False
    script_path = hermes_generated_script  # ← Layer 2 的脚本
```

### 位置2：`optimization_workflow.py` 中的脚本路径

**当前代码**：
```python
async def run(
    self,
    script_path: str,  # ← 接收脚本路径
    ...
):
    # 使用传入的脚本路径
    rl_result = await self.rl_optimizer.optimize(
        script_path=script_path,
        ...
    )
```

**改进**：
```python
async def run(
    self,
    script_path: str,  # ← 接收 Layer 2 的脚本路径
    ...
    directly_satisfied: bool = False,
):
    # 如果 Layer 2 已满足，直接使用 Layer 2 的脚本
    if directly_satisfied and initial_metrics:
        logger.info("[OptimWorkflow] Using Layer 2 script (directly_satisfied)")
        # 不重新生成脚本
        # 直接返回
        return {
            "status": "done",
            "best_params": initial_auto_params or {},
            "best_metrics": initial_metrics,
            "report_path": "",
        }
    
    # 如果 Layer 2 未满足，使用 Layer 2 的脚本进行参数优化
    logger.info("[OptimWorkflow] Using Layer 2 script for parameter optimization")
    rl_result = await self.rl_optimizer.optimize(
        script_path=script_path,  # ← Layer 2 的脚本
        ...
    )
```

---

## 配置改进

### 修改 `config.yaml`

```yaml
workflow:
  # Layer 3 是否执行 Hermes 生成脚本
  # true  → Layer 3 可以重新生成脚本（当前行为）
  # false → Layer 3 直接使用 Layer 2 的脚本（推荐）
  hermes_execution: false
```

---

## 工作流对比

### 改进前

```
Layer 2 Gate
  ├─ 生成脚本 A
  ├─ 运行仿真
  └─ 判断

Layer 3 RL 优化
  ├─ 重新生成脚本 B ❌ 不同
  ├─ 运行仿真
  └─ 判断 ❌ 结果不一致
```

### 改进后

```
Layer 2 Gate
  ├─ 生成脚本 A ✅
  ├─ 运行仿真
  └─ 判断

Layer 3 RL 优化
  ├─ 使用脚本 A ✅ 相同
  ├─ 运行仿真
  └─ 判断 ✅ 结果一致
```

---

## 快速修复

### 步骤1：禁用 Layer 3 脚本生成

**修改**：`config.yaml` 第152行

```yaml
# 原来：
hermes_execution: true

# 改为：
hermes_execution: false
```

### 步骤2：确保 Layer 3 使用 Layer 2 的脚本

**验证**：在 `cli_agent.py` 中确保 `script_path` 指向 Layer 2 生成的脚本

```python
# Layer 3 应该接收 Layer 2 的脚本路径
script_path = hermes_generated_script  # ← Layer 2 的脚本
```

---

## 预期效果

| 方面 | 改进前 | 改进后 | 改进 |
|------|--------|--------|------|
| **脚本一致性** | ❌ 不同 | ✅ 一致 | ✅ |
| **仿真结果** | ❌ 不一致 | ✅ 一致 | ✅ |
| **判断逻辑** | ❌ 混乱 | ✅ 清晰 | ✅ |
| **计算效率** | ❌ 重复生成 | ✅ 避免重复 | ✅ |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `config.yaml` | 152 | hermes_execution 配置 |
| `cli_agent.py` | 872 | Layer 3 Hermes 调用 |
| `optimization_workflow.py` | 57-69 | Layer 3 工作流入口 |

---

## 总结

**问题**：
- Layer 3 重新生成脚本，导致与 Layer 2 不一致

**用户建议**：
- Layer 3 应该使用 Layer 2 生成的脚本

**解决方案**：
1. 禁用 Layer 3 的脚本生成（hermes_execution=false）
2. Layer 3 直接使用 Layer 2 的脚本
3. 避免重复生成和不一致

**预期效果**：
- ✅ 脚本版本一致
- ✅ 仿真结果一致
- ✅ 判断逻辑清晰
- ✅ 计算效率高
