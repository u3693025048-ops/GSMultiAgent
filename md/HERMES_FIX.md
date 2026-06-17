# Hermes Agent 修复指南

## 问题诊断

**症状**：运行CLI时显示 "Hermes not available"

**根本原因**：`run_agent` 模块导入失败（第769-771行 hermes_integration.py）

```python
except ImportError as e:
    logger.warning(f"Hermes Agent not available: {e}")
    HermesIntegration = None
```

---

## 解决方案

### 方案1：检查Hermes依赖（推荐）

**步骤1**：检查是否安装了Hermes Agent

```bash
pip list | grep -i hermes
pip list | grep -i agent
```

**预期输出**：应该看到类似 `hermes-agent` 或 `run-agent` 的包

**步骤2**：如果未安装，安装Hermes Agent

```bash
# 方式1：从PyPI安装（如果可用）
pip install hermes-agent

# 方式2：从源代码安装（如果有本地副本）
pip install -e /path/to/hermes-agent

# 方式3：检查requirements.txt或setup.py
pip install -r requirements.txt
```

**步骤3**：验证安装

```bash
python -c "from run_agent import AIAgent; print('Hermes OK')"
```

**预期输出**：`Hermes OK`

---

### 方案2：检查Python路径

如果Hermes已安装但仍无法导入，可能是Python路径问题。

**步骤1**：检查PYTHONPATH

```bash
echo $PYTHONPATH
```

**步骤2**：添加Hermes路径到PYTHONPATH

```bash
# Linux/macOS
export PYTHONPATH="/path/to/hermes-agent:$PYTHONPATH"

# Windows (PowerShell)
$env:PYTHONPATH = "C:\path\to\hermes-agent;$env:PYTHONPATH"

# Windows (cmd)
set PYTHONPATH=C:\path\to\hermes-agent;%PYTHONPATH%
```

**步骤3**：重新运行CLI

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

### 方案3：调试导入错误

**步骤1**：获取详细错误信息

修改 `hermes_integration.py` 第769-771行：

```python
except ImportError as e:
    import traceback
    logger.error(f"Hermes Agent import failed: {e}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    HermesIntegration = None
```

**步骤2**：运行CLI并查看详细错误

```bash
python cli_agent.py --prompt "T4工况..." 2>&1 | grep -A 20 "Hermes Agent import failed"
```

**步骤3**：根据错误信息安装缺失的依赖

常见缺失依赖：
- `run_agent` - Hermes主模块
- `tools` - Hermes工具注册表
- `model_tools` - 模型工具库
- `asyncio` - 异步支持

---

## 验证Hermes是否正常工作

### 快速检查

```bash
python -c "
from multi_agent.integration.hermes_integration import HERMES_AVAILABLE, HermesIntegration
print(f'HERMES_AVAILABLE: {HERMES_AVAILABLE}')
print(f'HermesIntegration: {HermesIntegration}')
"
```

**预期输出**：
```
HERMES_AVAILABLE: True
HermesIntegration: <class 'multi_agent.integration.hermes_integration.HermesIntegration'>
```

### 完整初始化测试

```python
import asyncio
from multi_agent.integration.hermes_integration import HermesIntegration, HERMES_AVAILABLE

async def test_hermes():
    if not HERMES_AVAILABLE:
        print("Hermes not available")
        return
    
    hermes = HermesIntegration()
    success = await hermes.initialize()
    print(f"Hermes initialized: {success}")

asyncio.run(test_hermes())
```

---

## 常见问题排查

### Q1：ImportError: No module named 'run_agent'

**原因**：Hermes Agent未安装

**解决**：
```bash
pip install hermes-agent
# 或
pip install run-agent
```

### Q2：ImportError: No module named 'tools'

**原因**：Hermes工具模块未安装

**解决**：
```bash
pip install hermes-tools
# 或更新Hermes
pip install --upgrade hermes-agent
```

### Q3：ModuleNotFoundError in model_tools

**原因**：模型工具库缺失

**解决**：
```bash
pip install model-tools
# 或
pip install openai-tools
```

### Q4：Hermes初始化失败（initialize_with_tools返回False）

**原因**：可能是LLM配置问题或工具注册失败

**调试**：
1. 检查 `config.yaml` 中的LLM配置
2. 验证API密钥是否正确
3. 检查网络连接

```bash
# 查看详细日志
python cli_agent.py --prompt "..." 2>&1 | grep -i "hermes\|error\|failed"
```

---

## 配置Hermes（可选）

### 环境变量

```bash
# 设置LLM API密钥
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"

# 设置Hermes工具超时
export HERMES_TOOL_DISPATCH_TIMEOUT="1800"
```

### config.yaml配置

```yaml
llm:
  model: "gpt-4"
  provider: "openai"
  api_key: "${OPENAI_API_KEY}"
  base_url: "${OPENAI_BASE_URL}"

workflow:
  hermes_tool_timeout: 1800
```

---

## 如果Hermes仍然无法工作

### 降级方案：禁用Hermes

如果Hermes无法修复，可以禁用它，直接使用RL优化：

```yaml
# config.yaml
ablation:
  rl_optimization: true
  optimization_workflow: true
  parameter_experience_reuse: true
  reflection_agent: true
  hermes_rl_tool: false  # 禁用Hermes RL工具
```

这样系统会跳过Hermes的任务规划步骤，直接进行RL优化。

---

## 完整修复流程

1. **检查Hermes安装**
   ```bash
   pip list | grep -i hermes
   ```

2. **如果未安装，安装Hermes**
   ```bash
   pip install hermes-agent
   ```

3. **验证导入**
   ```bash
   python -c "from run_agent import AIAgent; print('OK')"
   ```

4. **运行CLI测试**
   ```bash
   python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
   ```

5. **观察日志**
   - 如果看到 "Hermes initialized" → 成功 ✅
   - 如果看到 "Hermes not available" → 返回步骤1

---

## 总结

| 问题 | 解决方案 |
|------|---------|
| ImportError: run_agent | `pip install hermes-agent` |
| ImportError: tools | `pip install --upgrade hermes-agent` |
| Hermes初始化失败 | 检查LLM配置和API密钥 |
| 仍然无法工作 | 禁用Hermes，使用直接RL模式 |

---

**预期结果**：修复后，CLI应该显示：
```
Hermes initialized with tools (task_prompt auto-injected).
```

而不是：
```
Hermes not available. Skipping task planning.
```
