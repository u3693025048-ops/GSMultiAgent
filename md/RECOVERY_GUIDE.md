# 系统恢复指南 - 物理限幄探测超时

## 快速恢复（3个选项）

### 选项1：修复MATLAB（推荐，5分钟）

```bash
# 1. 检查MATLAB许可证
matlab -r "license('test', 'all'); exit"

# 2. 清理MATLAB缓存
# Windows: 删除 %APPDATA%\MathWorks\MATLAB\R*\
# Linux: 删除 ~/.matlab/R*/

# 3. 重新运行
python cli_agent.py --file prompt.txt
```

### 选项2：使用Octave（快速，3分钟）

```bash
# 1. 修改配置
# 编辑 config.yaml，找到：
#   simulation:
#     engine: matlab
# 改为：
#   simulation:
#     engine: octave

# 2. 重新运行
python cli_agent.py --file prompt.txt
```

### 选项3：跳过物理限幄探测（最快，1分钟）

```bash
# 1. 修改配置
# 编辑 config.yaml，找到：
#   simulation:
#     physics_bounds_enabled: true
# 改为：
#   simulation:
#     physics_bounds_enabled: false

# 2. 重新运行
python cli_agent.py --file prompt.txt

# 注意：这样会失去物理限幄检查，不推荐
```

---

## 详细排查步骤

### 步骤1：检查MATLAB状态

```bash
# 检查许可证
matlab -r "license('test', 'all'); exit"

# 检查版本
matlab -r "version; exit"

# 测试启动时间
time matlab -r "exit"
```

### 步骤2：检查系统资源

```bash
# Windows
wmic OS get TotalVisibleMemorySize,FreePhysicalMemory
tasklist | find "MATLAB"
dir C:\Users\%USERNAME%\AppData\Local\Temp | find /c ":"

# Linux
free -h
ps aux | grep matlab
du -sh /tmp/
```

### 步骤3：清理缓存

```bash
# Windows
rmdir /s /q %APPDATA%\MathWorks\MATLAB\R*\
del /q %TEMP%\phys_bounds_*

# Linux
rm -rf ~/.matlab/R*/
rm -rf /tmp/phys_bounds_*
```

### 步骤4：增加超时时间（临时方案）

```bash
# 修改 layer2_script_gate.py 第195行
timeout_sec=240.0  # 从 180 改为 240

# 或设置环境变量
set MATLAB_TIMEOUT_SEC=240
python cli_agent.py --file prompt.txt
```

---

## 已生成的脚本信息

### 脚本位置

```
guidance_output/scripts/guidance_simulation_1781018750.m
```

### 脚本状态

```
✅ 已生成
✅ 语法检查通过
✅ 兼容性检查通过
❌ 物理限幄探测超时
```

### 脚本内容

```
- 修改后的制导律（gf函数）
- 保持原有接口兼容
- 符合MATLAB语法规范
```

---

## 恢复后的预期流程

```
1. 修复MATLAB或切换到Octave
   ↓
2. 重新运行 python cli_agent.py --file prompt.txt
   ↓
3. 物理限幄探测通过
   ↓
4. Layer 3 RL优化运行
   ↓
5. 生成最终优化结果
   ↓
6. 生成完整报告
```

---

## 常见问题

### Q1：为什么MATLAB启动这么慢？

**A**：可能原因：
- 许可证验证延迟
- 系统资源不足
- 磁盘I/O缓慢
- 防病毒软件干扰

**解决**：
- 检查许可证
- 清理缓存
- 增加超时时间
- 使用Octave

### Q2：Octave能替代MATLAB吗？

**A**：可以，但有限制：
- ✅ 基础MATLAB功能兼容
- ✅ 启动快3-5倍
- ⚠️ 某些高级功能可能不支持
- ⚠️ 需要确保脚本兼容

### Q3：跳过物理限幄探测安全吗？

**A**：不推荐：
- ❌ 失去安全检查
- ❌ 可能生成不稳定的制导律
- ⚠️ 仅作为最后手段

### Q4：如何手动运行已生成的脚本？

**A**：使用run_simulation工具：
```bash
run_simulation(
    script_path="guidance_output/scripts/guidance_simulation_1781018750.m",
    mission_conditions="RUN_CASE='T';SUB_IDX=4;",
    nmc=25
)
```

---

## 恢复检查清单

- [ ] 检查MATLAB许可证
- [ ] 检查系统资源（内存、CPU、磁盘）
- [ ] 清理MATLAB缓存
- [ ] 选择恢复方案（MATLAB修复 或 Octave）
- [ ] 修改配置（如需要）
- [ ] 重新运行优化
- [ ] 验证物理限幄探测通过
- [ ] 验证Layer 3 RL优化完成
- [ ] 生成最终报告

---

## 相关文档

| 文档 | 说明 |
|------|------|
| `SYSTEM_COMPLETION_STATUS.md` | 系统完成状态报告 |
| `PHYSICS_BOUNDS_TIMEOUT_DIAGNOSIS.md` | 物理限幄探测超时诊断 |
| `PHYSICS_BOUNDS_TIMEOUT_QUICK.md` | 快速修复指南 |

---

## 总结

**当前状态**：
- ✅ 95% 完成
- ❌ 物理限幄探测超时

**快速恢复**：
1. 修复MATLAB（推荐）
2. 或使用Octave
3. 或增加超时时间

**预期时间**：
- 修复MATLAB：5分钟
- 切换Octave：3分钟
- 重新运行：10-20分钟
- 总计：15-25分钟

**预期结果**：
- ✅ 物理限幄探测通过
- ✅ Layer 3 RL优化完成
- ✅ 生成最终优化结果
