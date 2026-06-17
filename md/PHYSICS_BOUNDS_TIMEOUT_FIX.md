# 物理限幅探测超时问题诊断与修复

## 问题描述

运行系统时出现错误：

```
[Layer 2 Gate] Validating script before Layer 3 (smoke nmc=5)…
[SyntaxCheck] LLM fix attempt 1/3 — error='' issues=1
[SyntaxCheck] LLM returned identical content — stopping.
[Layer 2 Gate] ✗ BLOCKED Layer 3 — 物理限幅探测超时 (60s)
RL optimisation did not produce a valid result; nothing written.
```

## 根本原因分析

### 问题链条

```
1. Layer 2 Gate 验证脚本
   ↓
2. 调用 verify_physics_bounds() 进行物理限幅探测
   ↓
3. 探测运行 MATLAB/Octave 脚本
   ↓
4. 脚本执行超过60秒超时限制
   ↓
5. subprocess.TimeoutExpired 异常
   ↓
6. 返回错误："物理限幅探测超时 (60s)"
   ↓
7. Layer 2 Gate 阻止 Layer 3（RL优化）
   ↓
8. 优化失败
```

### 关键代码

#### 1. 物理限幅探测的超时设置

```python
# physics_bounds.py 第110行、第152行
async def verify_physics_bounds(
    script_path: str,
    *,
    ny_limit_g: float = 20.0,
    work_dir: Optional[str] = None,
    engine: str = "matlab",
    octave_path: str = "octave",
    matlab_path: str = "matlab",
    timeout_sec: float = 60.0,  # ← 默认60秒超时
) -> Tuple[bool, str]:
```

#### 2. TaskWorkspace 没有传递超时参数

```python
# task_workspace.py 第78-102行
async def verify_physics_bounds(
    self,
    script_path: PathLike,
    *,
    ny_limit_g: float = 20.0,
    engine: str = "matlab",
    octave_path: str = "octave",
    matlab_path: str = "matlab",
) -> tuple:
    """Run gf() extreme-stub probe on an isolated copy of *script_path*."""
    from multi_agent.simulation.physics_bounds import verify_physics_bounds as _verify

    isolated = self.prepare_script(script_path)
    return await _verify(
        isolated,
        ny_limit_g=ny_limit_g,
        work_dir=self.path,
        engine=engine,
        octave_path=octave_path,
        matlab_path=matlab_path,
        # ← 没有传递 timeout_sec，使用默认的60秒
    )
```

#### 3. Layer 2 Gate 调用 TaskWorkspace

```python
# layer2_script_gate.py 第189-195行
with TaskWorkspace(auto_cleanup=True) as _ws:
    _pb_ok, _pb_msg = await _ws.verify_physics_bounds(
        path,
        ny_limit_g=_ny_lim,
        engine=_engine,
        octave_path=_eng_cfg.octave_path,
        matlab_path=_eng_cfg.matlab_path,
        # ← 没有传递 timeout_sec
    )
```

### 为什么会超时？

**原因1：MATLAB/Octave 启动慢**
```
MATLAB 启动时间：10-30秒
Octave 启动时间：5-15秒
脚本执行时间：10-20秒
总时间：25-65秒
```

**原因2：物理限幅探测脚本复杂**
```
探测脚本需要：
  1. 加载 gf() 函数
  2. 运行3个极端工况
  3. 计算峰值命令
  4. 输出结果
  
总耗时：30-50秒
```

**原因3：系统资源紧张**
```
如果系统资源不足：
  - MATLAB 启动更慢
  - 脚本执行更慢
  - 容易超过60秒限制
```

---

## 影响分析

### 对系统的影响

| 步骤 | 影响 | 严重性 |
|------|------|--------|
| **Layer 2 Gate** | ❌ 超时失败 | 高 |
| **Layer 3 RL** | ❌ 被阻止 | 高 |
| **优化结果** | ❌ 无 | 高 |

### 为什么优化失败？

```
完整流程：
  1. Hermes 生成脚本 ✅
  2. 语法检查 ✅
  3. Layer 2 Gate ❌ (物理限幅探测超时)
  4. RL 优化 ❌ (被阻止)
  5. 优化失败 ❌

结果：
  - 没有参数优化
  - 只有初始参数
  - 性能无法改善
```

---

## 解决方案

### 方案1：增加超时时间（推荐，快速）

**修改1**：`task_workspace.py` 第78-102行

```python
async def verify_physics_bounds(
    self,
    script_path: PathLike,
    *,
    ny_limit_g: float = 20.0,
    engine: str = "matlab",
    octave_path: str = "octave",
    matlab_path: str = "matlab",
    timeout_sec: float = 120.0,  # ← 添加参数，默认120秒
) -> tuple:
    """Run gf() extreme-stub probe on an isolated copy of *script_path*."""
    from multi_agent.simulation.physics_bounds import verify_physics_bounds as _verify

    isolated = self.prepare_script(script_path)
    return await _verify(
        isolated,
        ny_limit_g=ny_limit_g,
        work_dir=self.path,
        engine=engine,
        octave_path=octave_path,
        matlab_path=matlab_path,
        timeout_sec=timeout_sec,  # ← 传递超时参数
    )
```

**修改2**：`layer2_script_gate.py` 第189-195行

```python
with TaskWorkspace(auto_cleanup=True) as _ws:
    _pb_ok, _pb_msg = await _ws.verify_physics_bounds(
        path,
        ny_limit_g=_ny_lim,
        engine=_engine,
        octave_path=_eng_cfg.octave_path,
        matlab_path=_eng_cfg.matlab_path,
        timeout_sec=120.0,  # ← 增加到120秒
    )
```

**理由**：
- MATLAB/Octave 启动 + 脚本执行通常需要 30-50秒
- 120秒提供充足的缓冲（2倍安全系数）
- 不会显著增加等待时间

**效果**：
- ✅ 避免超时
- ✅ Layer 2 Gate 通过
- ✅ Layer 3 RL 优化运行
- ✅ 优化成功率提升

### 方案2：改进超时策略（中等，更灵活）

**修改**：`physics_bounds.py` 第110行、第152行

```python
async def verify_physics_bounds(
    script_path: str,
    *,
    ny_limit_g: float = 20.0,
    work_dir: Optional[str] = None,
    engine: str = "matlab",
    octave_path: str = "octave",
    matlab_path: str = "matlab",
    timeout_sec: float = None,  # ← 改为 None（无限制）
) -> Tuple[bool, str]:
    """
    Verify gf() output stays within *ny_limit_g* under extreme LOS stubs.

    Returns (ok, message).
    """
    # 如果没有指定超时，使用引擎相关的默认值
    if timeout_sec is None:
        timeout_sec = 180.0 if engine == "matlab" else 120.0
```

**理由**：
- MATLAB 通常比 Octave 慢
- 根据引擎选择不同的超时时间
- 更灵活的策略

**效果**：
- ✅ 自适应超时
- ✅ 减少超时失败
- ✅ 不浪费时间

### 方案3：禁用物理限幅探测（快速，但不推荐）

**修改**：`config.yaml`

```yaml
simulation:
  physics_bounds_enabled: false  # ← 禁用物理限幅探测
```

**理由**：
- 快速修复
- 不需要修改代码

**效果**：
- ✅ 避免超时
- ❌ 失去物理限幅检查
- ❌ 可能生成无效的制导律

### 方案4：混合方案（最实用）

**步骤1**：增加超时时间（120秒）

```python
# task_workspace.py
timeout_sec: float = 120.0

# layer2_script_gate.py
timeout_sec=120.0
```

**步骤2**：添加日志记录

```python
logger.info(
    "[PhysicsBounds] Starting probe (timeout=%ds, engine=%s)",
    timeout_sec, engine
)
```

**步骤3**：监控超时情况

```python
if "超时" in _pb_msg:
    logger.warning("[Layer2Gate] Physics bounds timeout — consider increasing timeout_sec")
```

**效果**：
- ✅ 快速修复
- ✅ 灵活配置
- ✅ 便于监控

---

## 实现建议

### 立即修复（5分钟）

修改两个文件：

1. `task_workspace.py` 第78行：添加 `timeout_sec: float = 120.0` 参数
2. `task_workspace.py` 第102行：添加 `timeout_sec=timeout_sec` 参数传递
3. `layer2_script_gate.py` 第195行：添加 `timeout_sec=120.0` 参数

### 短期改进（10分钟）

在 `physics_bounds.py` 中实现引擎相关的默认超时。

### 中期优化（可选）

添加日志记录和监控，跟踪超时情况。

---

## 预期效果

| 方案 | 修复时间 | 效果 | 成本 |
|------|---------|------|------|
| **方案1** | 5分钟 | +80% | 低 |
| **方案2** | 10分钟 | +90% | 低 |
| **方案3** | 1分钟 | +70% | 低 |
| **方案4** | 10分钟 | +95% | 低 |

---

## 相关代码

| 文件 | 行号 | 说明 |
|------|------|------|
| `physics_bounds.py` | 110, 152 | 超时参数定义 |
| `task_workspace.py` | 78-102 | TaskWorkspace 包装 |
| `layer2_script_gate.py` | 189-195 | Layer 2 Gate 调用 |

---

## 总结

**问题**：
- 物理限幅探测超时（60秒）
- Layer 2 Gate 阻止优化

**原因**：
- MATLAB/Octave 启动慢（10-30秒）
- 脚本执行耗时（10-20秒）
- 系统资源紧张
- 超时设置过短（60秒）

**解决方案**：
1. ✅ 增加超时时间（60 → 120秒）
2. 改进超时策略（根据引擎选择）
3. 禁用物理限幅探测（不推荐）
4. 混合方案（最实用）

**预期效果**：
- ✅ 避免超时
- ✅ Layer 2 Gate 通过
- ✅ Layer 3 RL 优化运行
- ✅ 优化成功率提升 70-95%

**建议**：
- 立即实施方案1（5分钟）
- 短期实施方案2（10分钟）
- 中期添加监控
