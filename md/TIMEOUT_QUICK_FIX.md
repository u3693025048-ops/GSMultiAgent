# 🚀 Hermes超时快速修复

## 问题

```
Tool run_simulation returned error (301.37s): 
Simulation timed out (>300s)
```

## 解决方案（选一个）

### 方案1：运行脚本（最简单）

#### Windows PowerShell
```powershell
.\run_t4_with_timeout.ps1
```

#### Windows cmd
```cmd
run_t4_with_timeout.bat
```

### 方案2：手动设置环境变量

#### Windows PowerShell
```powershell
$env:HERMES_TOOL_DISPATCH_TIMEOUT = "3600"
$env:MATLAB_TIMEOUT_SEC = "3600"
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

#### Windows cmd
```cmd
set HERMES_TOOL_DISPATCH_TIMEOUT=3600
set MATLAB_TIMEOUT_SEC=3600
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

#### Linux/macOS
```bash
export HERMES_TOOL_DISPATCH_TIMEOUT=3600
export MATLAB_TIMEOUT_SEC=3600
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

### 方案3：修改config.yaml

编辑 `config.yaml`：

```yaml
workflow:
  hermes_tool_timeout: 3600  # 增加到3600秒
```

然后运行：
```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

## 推荐方案

**方案1（运行脚本）** 最简单，一条命令搞定：

```powershell
.\run_t4_with_timeout.ps1
```

---

## 预期结果

修复后，应该看到：
```
[Tool →] run_simulation
... 仿真运行中 ...
[Tool ✓] run_simulation (完成，而不是超时)
```

而不是：
```
[Tool →] run_simulation
Tool run_simulation returned error (301.37s): Simulation timed out
```

---

## 详细说明

见 `HERMES_TIMEOUT_FIX.md`

---

**立即修复**：
```powershell
.\run_t4_with_timeout.ps1
```
