# 正确的工作流策略

## 问题诊断

之前的策略有误：

```
配置：hermes_execution=false

问题：
  ❌ 第一次迭代：Hermes 不执行 → 没有脚本生成
  ❌ Layer 2 Gate 回退到 KB 模板
  ❌ 无法进行 MODIFY_LAW（修改制导律）
```

---

## 正确的策略

### 核心原则

```
Layer 2（Hermes 执行）：
  ├─ 生成脚本（MODIFY_LAW 或 TUNE_PARAMS）
  ├─ 运行仿真（nmc=25）
  └─ 判断是否满足

Layer 3（RL 优化）：
  ├─ 使用 Layer 2 的脚本
  ├─ 修改参数（RL_PARAMS_BEGIN/END）
  ├─ 运行仿真（nmc=25）
  └─ 判断是否满足
```

### 配置

```yaml
workflow:
  max_iterations: 1
  hermes_execution: true  # ← Layer 2 执行 Hermes 生成脚本
```

---

## 完整的工作流

### 第一次迭代

```
Step 1：任务规划
  └─ 分析工况，确定设计路径（MODIFY_LAW / TUNE_PARAMS）

Step 2：Hermes 执行（hermes_execution=true）
  ├─ 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m
  ├─ 运行仿真（nmc=25）
  └─ 获得仿真结果

Step 2.5：Layer 2 Gate 验证
  ├─ 验证脚本有效性
  ├─ 运行烟雾测试（nmc=10）
  └─ 验证闭环快扫

Step 3：Layer 3 RL 优化
  ├─ 接收 Layer 2 的脚本
  ├─ 修改参数（RL_PARAMS_BEGIN/END）
  ├─ 运行仿真（nmc=25）
  └─ 判断是否满足

Step 3.5：反思智能体
  └─ 分析结果，提供建议

Step 4：参数经验保存
  └─ 保存优化结果

Step 5：生成报告
  └─ 输出优化报告
```

---

## 关键改进

### 1. 脚本保留机制

```python
# cli_agent.py 第2037-2046行
_gate_script = (
    hermes_generated_script  # 当前轮生成的脚本
    or matlab_script_path  # 上一轮的脚本
    or _find_latest_matlab_script(...)
    or KB_TEMPLATE
)
```

**效果**：
- ✅ 优先使用最新生成的脚本
- ✅ 回退到上一轮的脚本
- ✅ 最后回退到 KB 模板

### 2. 脚本路径保存

```python
# cli_agent.py 第2173-2176行
if _wf_script and os.path.isfile(_wf_script):
    matlab_script_path = _wf_script
```

**效果**：
- ✅ 保存本轮使用的脚本
- ✅ 供下一轮使用

### 3. 条件更新

```python
# cli_agent.py 第2073-2080行
if wf_cfg.hermes_execution:
    hermes_generated_script = _g_script
```

**效果**：
- ✅ 只在 Hermes 执行时更新
- ✅ 保留脚本路径

---

## 工作流对比

### 错误的策略（hermes_execution=false）

```
第一次迭代
  ├─ Hermes 不执行 ❌
  ├─ hermes_generated_script = ""
  ├─ Layer 2 Gate 回退到 KB 模板 ❌
  └─ 无法进行 MODIFY_LAW ❌
```

### 正确的策略（hermes_execution=true）

```
第一次迭代
  ├─ Hermes 执行 ✅
  ├─ 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m ✅
  ├─ Layer 2 Gate 验证脚本 ✅
  ├─ Layer 3 使用脚本进行参数优化 ✅
  └─ 获得优化结果 ✅
```

---

## 配置说明

### `config.yaml`

```yaml
workflow:
  # 最大迭代轮次
  max_iterations: 1
  
  # Hermes 执行开关
  # true  → Layer 2 执行 Hermes 生成脚本（推荐）
  # false → Layer 2 跳过 Hermes，直接使用已有脚本
  hermes_execution: true
  
  # Hermes 工具超时
  hermes_tool_timeout: 0

simulation:
  # Layer 2 烟雾测试样本数
  layer2_smoke_nmc: 25
  
  # 物理限幅探测
  physics_bounds_enabled: false
  
  # RL 优化配置
  rl_optimization:
    enabled: true
    max_episodes: 50
    nmc_per_eval: 25
```

---

## 预期行为

### 第一次迭代

```
[Step 2.5] Hermes Content Generation (mode=MODIFY_LAW)...
  ✓ Hermes 生成脚本

[Layer 2 Gate] Validating script before Layer 3...
  ✓ Layer 2 Gate 验证脚本

[Layer 3] Optimization Workflow | script=guidance_simulation_T4_MODIFY_LAW_1781107289.m
  ✓ Layer 3 使用脚本进行参数优化

[Step 4] ParameterExperience Writeback & Model File Saving...
  ✓ 保存优化结果

[Step 5] Generating Report...
  ✓ 生成报告
```

---

## 总结

**错误的策略**：
- ❌ hermes_execution=false
- ❌ 第一次迭代没有脚本生成
- ❌ 无法进行 MODIFY_LAW

**正确的策略**：
- ✅ hermes_execution=true
- ✅ Layer 2 执行 Hermes 生成脚本
- ✅ Layer 3 使用脚本进行参数优化
- ✅ 脚本保留机制保证一致性

**关键改进**：
1. ✅ 脚本保留机制（matlab_script_path）
2. ✅ 脚本选择优先级
3. ✅ 条件更新逻辑
