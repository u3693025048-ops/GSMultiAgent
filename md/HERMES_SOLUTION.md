# Hermes Agent 正常运行解决方案

## 问题

运行CLI时显示：
```
Hermes not available. Skipping task planning.
```

## 根本原因

`run_agent` 模块导入失败，导致 `HERMES_AVAILABLE = False`

```python
# hermes_integration.py 第769-771行
except ImportError as e:
    logger.warning(f"Hermes Agent not available: {e}")
    HermesIntegration = None
```

---

## 快速修复（3步）

### 步骤1：运行诊断脚本

```bash
python diagnose_hermes.py
```

**输出示例**：
```
✅ run_agent - OK
✅ tools.registry - OK
✅ model_tools - OK
✅ hermes_integration.py - OK
   HERMES_AVAILABLE: True
```

### 步骤2：如果诊断失败，安装Hermes

```bash
pip install hermes-agent
```

### 步骤3：验证修复

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

**预期输出**：
```
Hermes initialized with tools (task_prompt auto-injected).
```

---

## 详细修复步骤

### 方案A：标准安装（推荐）

```bash
# 1. 安装Hermes Agent
pip install hermes-agent

# 2. 验证安装
python -c "from run_agent import AIAgent; print('OK')"

# 3. 运行诊断
python diagnose_hermes.py

# 4. 测试CLI
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

### 方案B：从源代码安装

如果Hermes Agent在本地：

```bash
# 1. 找到Hermes Agent源代码路径
find ~ -name "run_agent" -type d 2>/dev/null

# 2. 从源代码安装
pip install -e /path/to/hermes-agent

# 3. 验证
python diagnose_hermes.py
```

### 方案C：使用requirements.txt

```bash
# 1. 检查是否有requirements.txt
ls requirements*.txt

# 2. 安装所有依赖
pip install -r requirements.txt

# 3. 验证
python diagnose_hermes.py
```

---

## 诊断工具使用

### 快速诊断

```bash
python diagnose_hermes.py
```

**输出内容**：
- ✅/❌ 核心Hermes模块检查
- ✅/❌ pip中的包检查
- ✅/❌ GSMultiAgent集成检查
- ✅/❌ LLM配置检查

### 详细诊断

如果诊断脚本显示失败，查看详细错误：

```bash
python -c "
from multi_agent.integration.hermes_integration import HERMES_AVAILABLE
print(f'HERMES_AVAILABLE: {HERMES_AVAILABLE}')

if not HERMES_AVAILABLE:
    try:
        from run_agent import AIAgent
    except ImportError as e:
        print(f'Import error: {e}')
        import traceback
        traceback.print_exc()
"
```

---

## 常见问题

### Q1：pip install hermes-agent 失败

**原因**：包不在PyPI中，或需要特殊源

**解决**：
```bash
# 方案1：从GitHub安装
pip install git+https://github.com/your-org/hermes-agent.git

# 方案2：从本地安装
pip install -e /local/path/to/hermes-agent

# 方案3：检查是否有其他包名
pip search hermes  # 或在PyPI网站搜索
```

### Q2：导入成功但Hermes仍然不可用

**原因**：可能是LLM配置问题

**解决**：
```bash
# 检查config.yaml中的LLM配置
cat config.yaml | grep -A 10 "^llm:"

# 确保API密钥已设置
echo $OPENAI_API_KEY
```

### Q3：Hermes初始化失败（initialize_with_tools返回False）

**原因**：工具注册失败或LLM连接问题

**解决**：
```bash
# 查看详细日志
python cli_agent.py --prompt "..." 2>&1 | grep -i "error\|failed\|hermes"

# 检查网络连接
ping api.openai.com

# 验证API密钥
python -c "import os; print('API_KEY:', os.getenv('OPENAI_API_KEY'))"
```

---

## 验证Hermes正常工作

### 方法1：检查日志输出

运行CLI后，应该看到：
```
[Step 2] Task Planning & Parameter Extraction...
  [Thinking] ...
  [Tool →] rag_retrieve
  [Tool ✓] rag_retrieve
  Hermes initialized with tools (task_prompt auto-injected).
```

### 方法2：检查Hermes变量

```python
from multi_agent.integration.hermes_integration import HERMES_AVAILABLE, HermesIntegration

print(f"HERMES_AVAILABLE: {HERMES_AVAILABLE}")  # 应该是 True
print(f"HermesIntegration: {HermesIntegration}")  # 应该是类，不是 None
```

### 方法3：测试Hermes初始化

```python
import asyncio
from multi_agent.integration.hermes_integration import HermesIntegration, HERMES_AVAILABLE

async def test():
    if not HERMES_AVAILABLE:
        print("Hermes not available")
        return False
    
    hermes = HermesIntegration()
    success = await hermes.initialize()
    print(f"Hermes initialized: {success}")
    return success

result = asyncio.run(test())
```

---

## 如果Hermes无法修复

### 降级方案：禁用Hermes

编辑 `config.yaml`：

```yaml
ablation:
  rl_optimization: true
  optimization_workflow: true
  parameter_experience_reuse: true
  reflection_agent: true
  hermes_rl_tool: false  # 禁用Hermes RL工具
```

这样系统会：
- ✅ 跳过Hermes任务规划
- ✅ 直接进行RL优化
- ✅ 仍然使用反射Agent进行早期退出

运行：
```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

## 总结

| 步骤 | 命令 | 预期结果 |
|------|------|---------|
| 1 | `python diagnose_hermes.py` | 显示所有检查结果 |
| 2 | `pip install hermes-agent` | 安装Hermes Agent |
| 3 | `python diagnose_hermes.py` | 所有检查通过 ✅ |
| 4 | `python cli_agent.py --prompt "..."` | Hermes初始化成功 |

---

## 相关文档

- `HERMES_FIX.md` - 详细修复指南
- `diagnose_hermes.py` - 诊断脚本
- `config.yaml` - 配置文件（LLM和Ablation设置）

---

**预期最终结果**：
```
Hermes initialized with tools (task_prompt auto-injected).
[Step 2] Task Planning & Parameter Extraction...
  [Thinking] Analyzing T4 flight condition...
  [Tool →] rag_retrieve
  [Tool ✓] rag_retrieve
  ...
```
