# Hermes仿真超时修复

## 问题

Hermes Agent在运行仿真时超时：
```
Tool run_simulation returned error (301.37s): 
Simulation timed out (>300s); set MATLAB_TIMEOUT_SEC env var to override
```

## 根本原因

1. **Hermes调用run_simulation时使用了高nmc值**（nmc=500, nmc=100）
2. **默认超时是300秒**，但仿真需要更长时间
3. **需要设置环境变量或config.yaml来增加超时时间**

---

## 快速修复（2种方案）

### 方案A：设置环境变量（推荐）

```bash
# Windows (PowerShell)
$env:HERMES_TOOL_DISPATCH_TIMEOUT = "3600"
$env:MATLAB_TIMEOUT_SEC = "3600"

# Windows (cmd)
set HERMES_TOOL_DISPATCH_TIMEOUT=3600
set MATLAB_TIMEOUT_SEC=3600

# Linux/macOS
export HERMES_TOOL_DISPATCH_TIMEOUT=3600
export MATLAB_TIMEOUT_SEC=3600
```

然后运行：
```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

### 方案B：修改config.yaml

编辑 `config.yaml`，找到 `workflow` 部分：

```yaml
workflow:
  hermes_tool_timeout: 3600  # 增加到3600秒（1小时）
```

然后运行：
```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

## 详细说明

### 超时时间计算

Hermes使用以下优先级计算超时时间：

```
优先级1: 环境变量 HERMES_TOOL_DISPATCH_TIMEOUT
优先级2: config.yaml workflow.hermes_tool_timeout
优先级3: 自动计算 = max(3600, max_episodes * nmc_per_eval * 120)
```

### 推荐超时时间

根据仿真配置：

| nmc值 | 预期时间 | 推荐超时 |
|------|---------|---------|
| 10 | 30秒 | 300秒 |
| 100 | 5分钟 | 600秒 |
| 500 | 25分钟 | 1800秒 |
| 1000 | 50分钟 | 3600秒 |

**对于T4工况**：
- Hermes可能会尝试nmc=500或更高
- **推荐超时时间：3600秒（1小时）**

---

## 完整修复步骤

### 步骤1：设置环境变量

```bash
# Windows PowerShell
$env:HERMES_TOOL_DISPATCH_TIMEOUT = "3600"
$env:MATLAB_TIMEOUT_SEC = "3600"

# 验证
echo $env:HERMES_TOOL_DISPATCH_TIMEOUT
echo $env:MATLAB_TIMEOUT_SEC
```

### 步骤2：运行T4优化

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

### 步骤3：观察日志

应该看到：
```
2026-06-05 15:15:10 - agent.tool_executor - INFO - Tool run_simulation started...
2026-06-05 15:20:10 - agent.tool_executor - INFO - Tool run_simulation completed (300s)
```

而不是：
```
2026-06-05 15:15:10 - agent.tool_executor - WARNING - Tool run_simulation returned error (301.37s): Simulation timed out
```

---

## 如果仍然超时

### 原因1：环境变量未生效

**检查**：
```bash
python -c "import os; print(os.getenv('HERMES_TOOL_DISPATCH_TIMEOUT'))"
```

**解决**：
- 重启IDE或终端
- 确保在正确的conda环境中

### 原因2：仿真确实需要更长时间

**解决**：
```bash
# 增加到2小时
$env:HERMES_TOOL_DISPATCH_TIMEOUT = "7200"
$env:MATLAB_TIMEOUT_SEC = "7200"
```

### 原因3：Hermes调用了太高的nmc值

**解决**：修改 `config.yaml` 限制Hermes的nmc：

```yaml
matlab_rl_optimizer:
  nmc_per_eval: 10  # 降低Hermes的nmc值
  max_episodes: 50
```

---

## 预防措施

### 1. 优化仿真速度

确保使用Octave而不是MATLAB（Octave更快）：
```bash
which octave  # Linux/macOS
where octave  # Windows
```

### 2. 减少蒙特卡洛样本

在 `config.yaml` 中：
```yaml
matlab_rl_optimizer:
  nmc_per_eval: 10  # 默认值，已经较小
```

### 3. 使用更快的LLM

在 `config.yaml` 中：
```yaml
llm:
  model: "deepseek-v4-pro"  # 已经很快
  # 或使用更快的模型
```

---

## 验证修复

运行诊断脚本：

```bash
python -c "
import os
print('HERMES_TOOL_DISPATCH_TIMEOUT:', os.getenv('HERMES_TOOL_DISPATCH_TIMEOUT', 'not set'))
print('MATLAB_TIMEOUT_SEC:', os.getenv('MATLAB_TIMEOUT_SEC', 'not set'))

from multi_agent.config_loader import get_config
cfg = get_config()
print('config.yaml hermes_tool_timeout:', getattr(getattr(cfg, 'workflow', None), 'hermes_tool_timeout', 'not set'))
"
```

**预期输出**：
```
HERMES_TOOL_DISPATCH_TIMEOUT: 3600
MATLAB_TIMEOUT_SEC: 3600
config.yaml hermes_tool_timeout: 3600
```

---

## 总结

| 步骤 | 命令 |
|------|------|
| 1 | `$env:HERMES_TOOL_DISPATCH_TIMEOUT = "3600"` |
| 2 | `$env:MATLAB_TIMEOUT_SEC = "3600"` |
| 3 | `python cli_agent.py --prompt "T4工况..."` |

---

## 相关文档

- `RUN_NOW.md` - 运行指南
- `HERMES_SOLUTION.md` - Hermes修复方案
- `config.yaml` - 配置文件

---

**预期结果**：仿真不再超时，Hermes可以正常完成任务规划和仿真
