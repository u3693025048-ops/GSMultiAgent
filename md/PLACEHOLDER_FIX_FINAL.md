# RL优化占位符sim_s修复方案

## 问题诊断

### 症状
- RL优化100轮后，所有迭代的指标完全相同或显示"完美"结果
- 参数注入对仿真结果没有影响
- MATLAB脚本执行时出现语法错误

### 根本原因
所有生成的MATLAB脚本都包含**占位符 `sim_s()` 函数**：

```matlab
% 占位符示例1（返回随机数）
function r = sim_s(p)
r.miss = 100*rand;
r.peak_ny = 30+5*randn;
r.pitch_pm = 45+5*randn;
r.bw_pitch = 10+randn;
r.gm_pitch = 6+randn;
end

% 占位符示例2（返回硬编码常数）
function r = sim_s(p)
r.miss = 0;
r.peak_ny = 0;
r.pitch_pm = 60;
r.bw_pitch = 25;
r.gm_pitch = 6;
end
```

**问题**：
- 完全忽略输入参数 `p`
- 返回随机数或硬编码常数
- 无论参数如何变化，仿真结果都相同
- 导致RL优化无法进行

## 解决方案

### 实现的修复

在 `multi_agent/rl/matlab_rl_optimizer.py` 中添加了：

#### 1. 占位符检测方法 `_detect_placeholder_sim_s()`

检测逻辑：
- 提取 `sim_s()` 函数体
- 计算非注释行数（< 10 行表示占位符）
- 检查是否调用真实仿真函数（rk4f、df、gf、cf、af）
- 检查是否返回硬编码常数或随机数
- **判定条件**：行数少 + 有硬编码返回 + 没有真实仿真函数调用 → 占位符

```python
is_placeholder = (
    len(body_lines) < 10
    and len(hardcoded_returns) >= 3
    and not is_real_sim
)
```

#### 2. 集成到RL流程

在 `_run_matlab_simulation()` 方法中，参数注入之前添加占位符检测：

```python
_placeholder_detected, _ = self._detect_placeholder_sim_s(content)
if _placeholder_detected:
    logger.error(
        f"  [RL] Detected placeholder sim_s in '{script_name}': "
        f"script contains a PLACEHOLDER sim_s that ignores parameters. "
        f"Metrics would be identical regardless of RL params. "
        f"Falling back to internal Python simulator."
    )
    return await self._run_internal_simulation(auto_params, mission_conditions)
```

### 为什么不注入真实sim_s？

最初尝试从KB模板注入真实的 `sim_s()` 函数，但遇到了MATLAB语法错误：
- 函数定义关闭不正确
- 与现有函数产生冲突
- 辅助函数（cg、rk4f、gf、cf等）可能不存在或位置不对

**更安全的方案**：检测到占位符时，直接使用内部Python模拟器，避免MATLAB脚本修改带来的风险。

## 修复效果

### 检测准确性

✅ **占位符检测**：准确识别返回随机数或硬编码常数的sim_s  
✅ **真实sim_s识别**：正确识别包含rk4f、gf、cf调用的真实仿真函数  
✅ **代码编译**：无语法错误  

### 运行时行为

当检测到占位符sim_s时：
1. 记录错误日志，说明检测到占位符
2. 自动切换到内部Python模拟器
3. 使用Python模拟器的仿真结果进行RL优化
4. **参数变化会真正影响仿真结果**
5. RL优化能够正常进行

### 日志示例

```
[RL] Detected placeholder sim_s in 'guidance_T4_APN_1780589744.m': 
script contains a PLACEHOLDER sim_s that ignores parameters. 
Metrics would be identical regardless of RL params. 
Falling back to internal Python simulator.
```

## 后续建议

### 1. 改进LLM生成流程

在 `generate_matlab_tool.py` 中添加验证，确保生成的脚本包含真实的仿真函数：

```python
is_placeholder, _ = _detect_placeholder_sim_s(generated_content)
if is_placeholder:
    logger.warning("Generated script contains placeholder sim_s")
    # 使用KB模板或要求LLM重新生成
```

### 2. 增强内容验证

在 `_looks_like_matlab_script()` 中添加检查，确保脚本包含真实的仿真函数：

```python
# Check for real simulation functions
if not any(fn in content for fn in ["rk4f", "function gf", "function cf"]):
    return False, "missing real simulation functions"
```

### 3. 使用KB模板作为后备

当检测到占位符时，考虑直接使用KB模板 `monte_carlo_single.m` 而不是LLM生成的脚本。

## 文件修改清单

- `multi_agent/rl/matlab_rl_optimizer.py`
  - 添加 `_detect_placeholder_sim_s()` 方法（行1432-1485）
  - 修改 `_run_matlab_simulation()` 方法，添加占位符检测（行1634-1647）
  - 移除了不稳定的注入逻辑

- `test_placeholder_detection.py` (新建)
  - 测试占位符检测功能
  - 所有测试通过 ✓

## 验证结果

```
Test 1 - Placeholder sim_s detection: ✓ PASS
Test 2 - Real sim_s detection: ✓ PASS
Test 3 - Detection on full script: ✓ PASS
```

## 总结

修复后，RL优化器会：
1. **自动检测**占位符sim_s
2. **立即切换**到内部Python模拟器
3. **避免MATLAB错误**
4. **确保参数生效**
5. **正常进行优化**

这是一个稳健的、防守性的解决方案，优先考虑可靠性而不是试图修复有问题的MATLAB脚本。
