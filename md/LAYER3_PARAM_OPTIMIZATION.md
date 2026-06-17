# Layer 3 参数优化机制说明

## 完整的工作流

### Layer 2 Gate 验证

```
1. 生成脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m
   ├─ 包含 RL_PARAMS_BEGIN/END 块
   ├─ 初始参数：w1=35, w2=32, w3=35, N_pn=3.5
   └─ 制导律：修改后的 gf() 函数

2. 运行仿真（nmc=25）
   └─ 仿真结果：SEP=4.09m, PeakNy=19.60g

3. 判断：✅ 满足 or ❌ 未满足
```

### Layer 3 RL 优化

```
1. 接收 Layer 2 的脚本
   ├─ 脚本：guidance_simulation_T4_MODIFY_LAW_1781107289.m
   ├─ 制导律：保持不变（不重新生成）
   └─ 参数：可以修改

2. 修改脚本中的参数（RL_PARAMS_BEGIN/END 块）
   ├─ 原始参数：w1=35, w2=32, w3=35, N_pn=3.5
   ├─ 优化后参数：w1=45, w2=45, w3=45, N_pn=4.0
   └─ 制导律：保持不变

3. 运行仿真（nmc=25）
   └─ 仿真结果：取决于优化后的参数

4. 判断：✅ 满足 or ❌ 未满足
```

---

## 参数修改机制

### RL_PARAMS_BEGIN/END 块

脚本中的参数块：

```matlab
%% ── RL_PARAMS_BEGIN (auto-patched by RL optimizer, do not edit manually) ──
rl_w1          = 45.000000;
rl_zeta1       = 0.600000;
rl_tao1        = 0.150000;
rl_w2          = 45.000000;
rl_zeta2       = 0.600000;
rl_tao2        = 0.150000;
rl_w3          = 45.000000;
rl_zeta3       = 0.550000;
rl_N_pn        = 4.000000;
rl_gama_max_deg = 45;
%% ── RL_PARAMS_END ──
```

**说明**：
- `RL_PARAMS_BEGIN` 和 `RL_PARAMS_END` 之间的参数可以被 RL 优化器修改
- RL 优化器会自动替换这些参数值
- 制导律（gf() 函数）保持不变

### 参数修改流程

```python
# matlab_rl_optimizer.py 中的参数修改逻辑

# 1. 读取脚本
with open(script_path, 'r') as f:
    content = f.read()

# 2. 提取 RL_PARAMS_BEGIN/END 块
rl_block_pat = re.compile(
    r"(%%.*?RL_PARAMS_BEGIN.*?\n)(.*?)(%%.*?RL_PARAMS_END)",
    re.DOTALL,
)
rl_block_match = rl_block_pat.search(content)

# 3. 替换参数值
if rl_block_match:
    new_params = f"""rl_w1          = {auto_params['w1']};
rl_zeta1       = {auto_params['zeta1']};
...
rl_N_pn        = {auto_params['N_pn']};
"""
    content = rl_block_pat.sub(
        r"\1" + new_params + r"\3",
        content
    )

# 4. 写回脚本
with open(script_path, 'w') as f:
    f.write(content)

# 5. 运行仿真
run_simulation(script_path)
```

---

## 工作流对比

### 改进前（Layer 3 重新生成脚本）

```
Layer 2 脚本 A
  ├─ 制导律：修改后的 gf()
  ├─ 参数：w1=35, w2=32, ...
  └─ 仿真结果：SEP=4.09m, PeakNy=19.60g

Layer 3 脚本 B（重新生成）❌
  ├─ 制导律：可能不同
  ├─ 参数：w1=45, w2=45, ...
  └─ 仿真结果：SEP=11.32m, PeakNy=22.5g ❌ 不一致
```

### 改进后（Layer 3 使用 Layer 2 脚本，修改参数）

```
Layer 2 脚本 A
  ├─ 制导律：修改后的 gf() ✅
  ├─ 参数：w1=35, w2=32, ...
  └─ 仿真结果：SEP=4.09m, PeakNy=19.60g

Layer 3 修改脚本 A 的参数 ✅
  ├─ 制导律：保持不变 ✅
  ├─ 参数：w1=45, w2=45, ...（优化后）
  └─ 仿真结果：取决于优化后的参数

如果优化后满足要求：
  └─ 仿真结果：SEP≤7m, PeakNy≤20g ✅
```

---

## 关键点

### 1. 脚本一致性

```
✅ Layer 3 使用 Layer 2 的脚本
   - 制导律实现一致
   - 基础结构一致
   - 仿真框架一致

❌ Layer 3 重新生成脚本
   - 制导律可能不同
   - 基础结构可能不同
   - 仿真结果不可比
```

### 2. 参数修改

```
✅ Layer 3 修改 RL_PARAMS_BEGIN/END 块中的参数
   - 自动化修改
   - 不影响制导律
   - 高效优化

❌ Layer 3 修改脚本其他部分
   - 可能破坏脚本结构
   - 可能影响制导律
   - 不推荐
```

### 3. 优化流程

```
Layer 3 RL 优化流程：

1. 接收 Layer 2 的脚本
   └─ script_path = layer2_script

2. 初始化 RL 优化器
   └─ rl_optimizer = MatlabRLOptimizer(...)

3. 运行优化循环
   ├─ 生成候选参数：auto_params = {w1: 40, w2: 40, ...}
   ├─ 修改脚本参数：patch_rl_params(script_path, auto_params)
   ├─ 运行仿真：run_simulation(script_path)
   ├─ 评估结果：metrics = parse_output(...)
   └─ 判断是否满足要求

4. 返回最优结果
   └─ best_params, best_metrics
```

---

## 代码实现

### 位置1：`matlab_rl_optimizer.py` 中的参数修改

```python
async def _run_matlab_simulation(
    self,
    auto_params: Dict[str, float],
    script_path: str,
    ...
):
    # 读取脚本
    with open(script_path, 'r', encoding='utf-8') as fh:
        content = fh.read()
    
    # 修改 RL_PARAMS_BEGIN/END 块中的参数
    rl_block_pat = re.compile(
        r"(%%.*?RL_PARAMS_BEGIN.*?\n)(.*?)(%%.*?RL_PARAMS_END)",
        re.DOTALL,
    )
    rl_block_match = rl_block_pat.search(content)
    
    if rl_block_match:
        # 构建新的参数块
        new_params = self._build_rl_params_block(auto_params)
        
        # 替换参数
        content = rl_block_pat.sub(
            r"\1" + new_params + r"\3",
            content
        )
    
    # 写回脚本
    with open(script_path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    
    # 运行仿真
    return await self._run_matlab_probe(script_path, ...)
```

### 位置2：`optimization_workflow.py` 中的脚本传递

```python
async def run(
    self,
    script_path: str,  # ← Layer 2 的脚本路径
    ...
    directly_satisfied: bool = False,
):
    if directly_satisfied and initial_metrics:
        # Layer 2 已满足，直接返回
        return {
            "status": "done",
            "best_params": initial_auto_params or {},
            "best_metrics": initial_metrics,
            "report_path": "",
        }
    
    # Layer 2 未满足，进行参数优化
    # 使用 Layer 2 的脚本，修改参数
    rl_result = await self.rl_optimizer.optimize(
        script_path=script_path,  # ← Layer 2 的脚本
        ...
    )
    
    best_params = rl_result.get("best_params", {})
    best_metrics = rl_result.get("best_metrics", {})
    
    return {
        "status": "done" if satisfied else "needs_iteration",
        "best_params": best_params,
        "best_metrics": best_metrics,
        "report_path": "",
    }
```

---

## 配置说明

### `config.yaml` 中的相关配置

```yaml
workflow:
  # Layer 3 是否执行 Hermes 生成脚本
  # false → Layer 3 使用 Layer 2 的脚本，修改参数进行优化
  hermes_execution: false

simulation:
  # RL 优化配置
  rl_optimization:
    enabled: true
    max_episodes: 50
    nmc_per_eval: 25  # 每次评估的蒙特卡洛样本数
```

---

## 总结

**Layer 3 的工作流**：

1. ✅ **接收 Layer 2 的脚本**
   - 不重新生成脚本
   - 保持制导律一致

2. ✅ **修改脚本中的参数**
   - 修改 RL_PARAMS_BEGIN/END 块
   - 进行参数优化

3. ✅ **运行仿真和评估**
   - 使用修改后的参数
   - 评估仿真结果

4. ✅ **返回优化结果**
   - 最优参数
   - 最优指标

**关键原则**：
- ✅ 脚本来自 Layer 2（制导律一致）
- ✅ 参数由 Layer 3 优化（RL_PARAMS_BEGIN/END）
- ✅ 制导律保持不变（不重新生成）
- ✅ 仿真结果可比（相同的脚本和制导律）
