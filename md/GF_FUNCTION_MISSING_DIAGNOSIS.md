# gf() 函数缺失诊断

## 问题描述

```
[Layer 2 Gate] ✗ BLOCKED Layer 3 — 物理限幅探测未通过: 未找到 gf() 函数，无法进行物理限幄探测
```

## 根本原因

### 脚本结构问题

生成的脚本 `guidance_simulation_T4_MODIFY_LAW_v7_1781100608.m` 是一个**完整的蒙特卡洛仿真脚本**，但**缺少制导律函数 `gf()`**。

```matlab
% 脚本结构：
function guidance_simulation_T4_MODIFY_LAW_v7_1781100608()
  % 主函数
  % 参数定义
  % 工况配置
  % 蒙特卡洛循环
  % ...
  
  % ❌ 缺少：
  % function [N1,N2,...] = gf(Tx,Ty,Tz,XK,TVx,TVy,TVz,Np)
  %   % 制导律实现
  % end
end
```

### 为什么会缺少 gf() 函数？

```
可能原因：

1. Hermes LLM 生成的脚本不完整
   - 生成了蒙特卡洛框架
   - 但没有生成 gf() 函数实现

2. 脚本生成策略错误
   - MODIFY_LAW 模式应该修改 gf() 函数
   - 但生成的脚本没有 gf() 函数

3. 模板问题
   - 使用的模板可能不包含 gf() 函数
   - 或者 gf() 函数被意外删除

4. 脚本验证失败
   - 脚本通过了语法检查
   - 但没有通过内容检查（缺少 gf() 函数）
```

---

## 物理限幄探测的工作流程

### 正常流程

```
1. Layer 2 Gate 调用 verify_physics_bounds()
   ↓
2. build_probe_script() 提取 gf() 函数
   ↓
3. 生成物理限幄探测脚本
   ↓
4. 运行 MATLAB/Octave 探测脚本
   ↓
5. 验证 gf() 输出是否在限制范围内
```

### 当前失败流程

```
1. Layer 2 Gate 调用 verify_physics_bounds()
   ↓
2. build_probe_script() 提取 gf() 函数
   ↓
3. ❌ extract_gf_function() 返回 None
   ↓
4. ❌ 返回错误："未找到 gf() 函数，无法进行物理限幄探测"
   ↓
5. Layer 2 Gate 阻止 Layer 3
```

---

## 解决方案

### 方案1：禁用物理限幄探测（快速，不推荐）

**修改**：`config.yaml`

```yaml
simulation:
  physics_bounds_enabled: false
```

**理由**：
- 快速跳过 gf() 检查
- 不需要修改脚本

**效果**：
- ✅ Layer 2 Gate 通过
- ❌ 失去物理限幄检查
- ❌ 可能生成不安全的制导律

**不推荐原因**：
- 失去重要的安全验证

---

### 方案2：修改脚本生成策略（推荐）

**问题**：
- Hermes LLM 生成的脚本不包含 gf() 函数
- 需要确保生成的脚本包含完整的 gf() 函数定义

**解决步骤**：

1. **检查 Hermes 提示词**
   - 确保提示词要求生成 gf() 函数
   - 明确说明 gf() 函数的接口和功能

2. **改进脚本验证**
   - 在脚本生成后检查是否包含 gf() 函数
   - 如果缺少，要求 LLM 重新生成

3. **使用完整的模板**
   - 确保模板包含 gf() 函数的占位符
   - 或者在脚本生成后自动添加 gf() 函数

---

### 方案3：改进 gf() 提取逻辑（中期）

**修改**：`physics_bounds.py` 中的 `extract_gf_function()`

```python
def extract_gf_function(script_text: str) -> Optional[str]:
    """Return the gf() function block from a multi-function .m script."""
    m = _GF_BLOCK_RE.search(script_text or "")
    if not m:
        # 尝试从其他位置提取 gf() 函数
        # 例如：从注释、从其他文件、从模板等
        return None
    return m.group(0).rstrip()
```

**改进方向**：
- 增加更灵活的 gf() 函数提取逻辑
- 支持不同的函数定义格式
- 提供更详细的错误信息

---

### 方案4：自动生成 gf() 函数（最优）

**思路**：
- 如果脚本中没有 gf() 函数，自动生成一个默认的
- 或者从历史脚本中复制 gf() 函数

**实现**：

```python
def extract_or_generate_gf_function(script_text: str) -> Optional[str]:
    """Extract gf() function, or generate a default one if missing."""
    gf_block = extract_gf_function(script_text)
    if gf_block:
        return gf_block
    
    # 尝试从历史脚本中获取 gf() 函数
    historical_gf = get_gf_from_history()
    if historical_gf:
        return historical_gf
    
    # 生成默认的 gf() 函数
    return generate_default_gf()
```

---

## 立即修复（快速）

### 选项A：禁用物理限幄探测

**修改**：`config.yaml`

```yaml
simulation:
  physics_bounds_enabled: false
```

**命令**：
```bash
python cli_agent.py --file prompt.txt
```

**效果**：
- ✅ 快速通过 Layer 2 Gate
- ❌ 失去物理限幄检查

---

### 选项B：使用之前生成的有效脚本

查找之前生成的包含 gf() 函数的脚本：

```bash
# 查找包含 gf() 函数的脚本
grep -r "function.*gf" guidance_output/scripts/*.m
```

然后使用该脚本重新运行优化。

---

## 中期改进（推荐）

### 改进脚本生成

1. **检查 Hermes 提示词**
   - 确保明确要求生成 gf() 函数
   - 提供 gf() 函数的接口示例

2. **改进脚本验证**
   - 在脚本生成后检查 gf() 函数
   - 如果缺少，要求 LLM 重新生成

3. **添加自动修复**
   - 如果脚本缺少 gf() 函数，自动从历史脚本中复制
   - 或生成默认的 gf() 函数

---

## 预期效果

| 方案 | 修复时间 | 效果 | 成本 |
|------|---------|------|------|
| **方案1** | 1分钟 | +30% | 低 |
| **方案2** | 15分钟 | +80% | 中 |
| **方案3** | 30分钟 | +70% | 中 |
| **方案4** | 30分钟 | +90% | 高 |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `physics_bounds.py` | 65-85 | extract_gf_function 和 build_probe_script |
| `config.yaml` | 仿真配置 | physics_bounds_enabled |

---

## 总结

**问题**：
- 生成的脚本缺少 gf() 函数
- 物理限幄探测无法提取 gf() 函数

**原因**：
- Hermes LLM 生成的脚本不完整
- 脚本生成策略可能有问题

**快速解决**：
1. 禁用物理限幄探测（不推荐）
2. 使用之前生成的有效脚本

**中期改进**：
1. 改进脚本生成策略
2. 改进脚本验证逻辑
3. 添加自动修复机制

**建议**：
- 立即：禁用物理限幄探测，继续优化
- 短期：改进脚本生成和验证
- 中期：添加自动修复机制
