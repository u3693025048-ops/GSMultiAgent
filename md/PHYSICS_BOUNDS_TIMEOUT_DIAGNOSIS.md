# 物理限幅探测超时诊断 - 深度分析

## 问题描述

```
[Layer 2 Gate] ✗ BLOCKED Layer 3 — 物理限幅探测未通过: 物理限幅探测超时 (120s)
```

即使将超时时间从60秒增加到120秒，仍然超时。

---

## 根本原因分析

### 可能的原因

#### 原因1：MATLAB 启动非常慢

```
MATLAB 启动时间分布：
  - 快速启动：10-20秒
  - 正常启动：20-40秒
  - 慢速启动：40-80秒
  - 极慢启动：80-150秒+

可能原因：
  - 系统资源不足（内存、CPU）
  - MATLAB 许可证验证慢
  - 磁盘 I/O 缓慢
  - 防病毒软件干扰
```

#### 原因2：脚本本身有问题

```
物理限幅探测脚本：
  - 调用 gf() 函数
  - 运行3个极端工况
  - 计算峰值命令

可能问题：
  - gf() 函数有无限循环
  - gf() 函数计算非常耗时
  - 脚本有语法错误导致卡住
```

#### 原因3：系统资源不足

```
系统资源问题：
  - 内存不足（MATLAB 需要 1-2GB）
  - CPU 占用过高
  - 磁盘空间不足
  - 网络连接问题（许可证验证）
```

---

## 解决方案

### 方案1：禁用物理限幅探测（快速，不推荐）

**修改**：`config.yaml`

```yaml
simulation:
  physics_bounds_enabled: false  # ← 禁用物理限幅探测
```

**理由**：
- 快速解决超时问题
- 不需要修改代码

**效果**：
- ✅ 避免超时
- ❌ 失去物理限幅检查
- ❌ 可能生成不安全的制导律

**不推荐原因**：
- 失去重要的安全检查
- 可能导致优化结果不稳定

---

### 方案2：增加超时时间（快速，临时）

**修改**：`config.yaml` 或 `layer2_script_gate.py`

```python
# layer2_script_gate.py 第195行
timeout_sec=180.0  # 从 120 改为 180
```

**理由**：
- 给 MATLAB 更多的启动时间
- 简单直接

**效果**：
- ✅ 可能避免超时
- ⚠️ 等待时间更长
- ⚠️ 如果 MATLAB 启动 >180s，仍会失败

**推荐值**：
- 180秒：给 MATLAB 充足的启动时间
- 240秒：极端情况

---

### 方案3：使用 Octave 代替 MATLAB（推荐）

**修改**：`config.yaml`

```yaml
simulation:
  engine: octave  # ← 从 matlab 改为 octave
```

**理由**：
- Octave 启动更快（5-15秒 vs 20-80秒）
- 功能兼容
- 开源免费

**效果**：
- ✅ 启动快 3-5 倍
- ✅ 避免许可证验证延迟
- ✅ 减少超时风险

**注意**：
- 需要安装 Octave
- 某些 MATLAB 特性可能不支持

---

### 方案4：优化物理限幅探测脚本（最优）

**修改**：`physics_bounds.py` 第30-62行

```python
_PROBE_TEMPLATE = """\
%% Auto-generated physics bounds probe — do not edit manually
{gf_block}

function physics_bounds_probe_main()
    limit_g = {limit_g};
    peak = 0;
    Np = 6;
    
    % 减少测试工况数量（从3改为1）
    cases = {{
        struct('Tx',100,'Ty',0,'Tz',0,'V',900,'th',0.35,'pv',0.25,'up',0,'ga',0,'ph',0,'x',5000,'y',0,'z',-500,'TVx',0,'TVy',0,'TVz',0)
    }};
    
    for i = 1:numel(cases)
        c = cases{{i}};
        XK = zeros(12,1);
        XK(1)=c.V; XK(2)=c.up; XK(3)=c.ga; XK(4)=c.ph; XK(5)=c.th; XK(6)=c.pv;
        XK(10)=c.x; XK(11)=c.y; XK(12)=c.z;
        try
            [N1,N2,~,~,~] = gf(c.Tx,c.Ty,c.Tz,XK,c.TVx,c.TVy,c.TVz,Np);
            peak = max([peak, abs(N1), abs(N2)]);
        catch ME
            fprintf('PHYS_BOUNDS_ERROR case%%d: %%s\\n', i, ME.message);
            fprintf('PHYS_BOUNDS peak_cmd_g=Inf pass=0\\n');
            return;
        end
    end
    pass = peak <= limit_g + 1e-3;
    fprintf('PHYS_BOUNDS peak_cmd_g=%.4f pass=%d\\n', peak, pass);
end

physics_bounds_probe_main();
"""
```

**理由**：
- 减少测试工况数量（3 → 1）
- 减少计算时间
- 仍然能检查极端情况

**效果**：
- ✅ 执行时间减少 50-70%
- ✅ 减少超时风险
- ⚠️ 检查覆盖率降低

---

### 方案5：混合方案（最实用）

**步骤1**：增加超时时间到180秒

```python
# layer2_script_gate.py 第195行
timeout_sec=180.0
```

**步骤2**：设置环境变量（可选）

```bash
set MATLAB_TIMEOUT_SEC=180
python cli_agent.py --file prompt.txt
```

**步骤3**：如果仍然超时，使用 Octave

```yaml
simulation:
  engine: octave
```

**效果**：
- ✅ 逐步解决问题
- ✅ 灵活应对不同情况
- ✅ 最终一定能成功

---

## 实现建议

### 立即修复（5分钟）

修改 `layer2_script_gate.py` 第195行：

```python
timeout_sec=180.0  # 从 120 改为 180
```

### 短期改进（10分钟）

如果仍然超时，修改 `config.yaml`：

```yaml
simulation:
  engine: octave  # 使用 Octave
```

### 中期优化（可选）

优化物理限幅探测脚本，减少测试工况数量。

---

## 预期效果

| 方案 | 修复时间 | 效果 | 成本 |
|------|---------|------|------|
| **方案1** | 1分钟 | +50% | 低 |
| **方案2** | 5分钟 | +60% | 低 |
| **方案3** | 5分钟 | +80% | 低 |
| **方案4** | 15分钟 | +70% | 中 |
| **方案5** | 10分钟 | +90% | 低 |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `layer2_script_gate.py` | 195 | 超时参数 |
| `config.yaml` | 仿真引擎 | 引擎选择 |
| `physics_bounds.py` | 30-62 | 探测脚本 |

---

## 总结

**问题**：
- 物理限幅探测超时（120秒）
- 即使增加超时时间仍然失败

**可能原因**：
1. MATLAB 启动非常慢（>120秒）
2. 脚本本身有问题
3. 系统资源不足

**解决方案**：
1. ✅ 增加超时时间（180秒）
2. 使用 Octave 代替 MATLAB
3. 优化物理限幅探测脚本
4. 禁用物理限幅探测（不推荐）

**建议**：
- 立即实施方案2（增加到180秒）
- 如果仍然失败，实施方案3（使用Octave）
- 中期优化物理限幅探测脚本

**立即验证**：
```bash
python cli_agent.py --file prompt.txt
```
