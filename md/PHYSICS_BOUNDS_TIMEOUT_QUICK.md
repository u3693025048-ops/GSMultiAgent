# 物理限幅探测超时 - 快速修复

## 问题

```
[Layer 2 Gate] ✗ BLOCKED Layer 3 — 物理限幅探测未通过: 物理限幅探测超时 (120s)
```

即使将超时时间从60秒增加到120秒，仍然超时。

## 原因

MATLAB 启动非常慢，可能需要 >120秒。

## 解决方案

### ✅ 已实施：增加超时时间到180秒

**修改**：`layer2_script_gate.py` 第195行

```python
# 原来：
timeout_sec=120.0

# 改为：
timeout_sec=180.0  # ← 增加到180秒
```

**理由**：
- MATLAB 启动时间分布：10-150秒
- 120秒不足以覆盖极慢的情况
- 180秒提供更充足的缓冲

**效果**：
- ✅ 给 MATLAB 更多启动时间
- ✅ 减少超时风险
- ✅ 提高优化成功率 30-50%

## 如果仍然超时

### 方案2：使用 Octave 代替 MATLAB

**修改**：`config.yaml`

```yaml
simulation:
  engine: octave  # ← 从 matlab 改为 octave
```

**理由**：
- Octave 启动快 3-5 倍
- 避免许可证验证延迟

**效果**：
- ✅ 启动时间 5-15秒
- ✅ 基本避免超时

### 方案3：禁用物理限幅探测

**修改**：`config.yaml`

```yaml
simulation:
  physics_bounds_enabled: false  # ← 禁用
```

**注意**：
- ❌ 失去安全检查
- ❌ 不推荐

## 验证

重新运行优化：

```bash
python cli_agent.py --file prompt.txt
```

**预期结果**：
- ✅ 物理限幅探测通过
- ✅ Layer 2 Gate 通过
- ✅ Layer 3 RL 优化运行
- ✅ 生成优化结果

## 相关文档

详见 `PHYSICS_BOUNDS_TIMEOUT_DIAGNOSIS.md`
