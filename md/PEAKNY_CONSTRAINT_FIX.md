# PeakNy 约束评估修复 - 方案B（最大值）

## 问题

T4工况iter6出现**两层评估系统的矛盾**：

```
Layer 2 (judge_requirements): satisfied = TRUE
  └─ PeakNy(平均值) 17.23g <= 20g [OK]

Reflection Agent: needs_optimization = TRUE
  ├─ PeakNy(平均值) 17.23g 达标 ✅
  └─ PeakNy(最大值) 27.37g 超标 ❌ (超限37%)

结果：系统判定已达标，但Reflection认为需要继续优化
```

---

## 根本原因

**原始代码**（judge_requirements_tool.py）只检查**平均值**：

```python
pny = metrics.get("peak_ny", 0.0)  # 平均值 17.23g
ok = pny <= reqs["peak_ny_max"]    # 17.23g <= 20g → True
# 但忽视了 peak_ny_max = 27.37g ❌
```

**问题**：
- 导弹需要在**所有工况**下都满足过载限制
- 不能因为平均值达标就忽视极端工况
- 最大值27.37g超标意味着在某个特定工况下，导弹过载超限

---

## 解决方案B：使用最大值（更严格）

### 修改逻辑

**改为优先检查最大值**：

```python
if "peak_ny_max" in reqs:
    # Use MAXIMUM PeakNy value (most strict)
    pny_avg = metrics.get("peak_ny", 0.0)      # 平均值 17.23g
    pny_max = metrics.get("peak_ny_max", 0.0)  # 最大值 27.37g
    
    if pny_max > 0.0:
        ok = pny_max <= reqs["peak_ny_max"]    # 27.37g <= 20g → False ❌
        satisfied = satisfied and ok
        reasons.append(
            f"PeakNy(最大值) {pny_max:.2f}g {'<=' if ok else '>'} 要求 {reqs['peak_ny_max']:.2f}g"
            + (" [OK]" if ok else " [NG]")
        )
    elif pny_avg > 0.0:
        # Fallback: 如果没有最大值，使用平均值
        ok = pny_avg <= reqs["peak_ny_max"]
        satisfied = satisfied and ok
```

### 修改后的行为

```
iter6: 
  ├─ Layer 2: satisfied = False (因为 PeakNy max 27.37g > 20g)
  ├─ 进入 RL 优化
  ├─ 改进参数，降低 PeakNy 最大值
  └─ 最终达标：PeakNy avg=17g, max=19g ✅
```

---

## 修改文件

**`judge_requirements_tool.py` 第105-129行**

- **原始**：仅检查 `peak_ny`（平均值）
- **修复**：优先检查 `peak_ny_max`（最大值），fallback到平均值

---

## 工程意义

### 为什么要检查最大值？

1. **安全性**
   - 导弹在极端工况下也要满足过载限制
   - 不能因为平均值达标就忽视极端工况

2. **可靠性**
   - 极端工况虽然概率低，但一旦发生就会导致失控
   - 必须确保在所有工况下都满足约束

3. **一致性**
   - 与Reflection Agent的评估逻辑一致
   - 避免两层评估矛盾

### 极端工况分析

```
20轮蒙特卡洛仿真中：
├─ 大部分工况：PeakNy ≈ 17g（达标）
├─ 少数工况：PeakNy ≈ 27g（超标）
└─ 原因：目标机动与导弹响应同相时的极端情况
```

这种极端工况虽然概率低，但一旦发生就会导致导弹失控，必须避免。

---

## 评估逻辑对比

### 原始逻辑（仅平均值）

| 指标 | 值 | 要求 | 判定 |
|------|-----|------|------|
| PeakNy(平均值) | 17.23g | ≤20g | ✅ 达标 |
| PeakNy(最大值) | 27.37g | ≤20g | ❌ 超标 |
| **整体判定** | - | - | **✅ 达标**（错误） |

### 修复后的逻辑（最大值优先）

| 指标 | 值 | 要求 | 判定 |
|------|-----|------|------|
| PeakNy(平均值) | 17.23g | ≤20g | ✅ 达标 |
| PeakNy(最大值) | 27.37g | ≤20g | ❌ 超标 |
| **整体判定** | - | - | **❌ 未达标**（正确） |

---

## 预期效果

### 修复前
```
iter6: Layer2 satisfied=True → 跳过RL → Reflection 判定需要优化 → 继续迭代
```

### 修复后
```
iter6: Layer2 satisfied=False → 进入RL优化 → 改进PeakNy最大值 → 最终达标
```

### 优势

✅ **两层评估逻辑一致**  
✅ **更严格的约束检查**  
✅ **更安全的优化结果**  
✅ **避免虚假达标**  

---

## 优化建议

当PeakNy最大值超标时，可以：

1. **降低w1**（从46.25 → 40）
   - 减少自动驾驶仪响应速度
   - 降低极端工况下的过载

2. **增加zeta1**（从0.35 → 0.50）
   - 增加阻尼
   - 减少振荡和超调

3. **增加tao1**（从0.086 → 0.15）
   - 增加滞后时间
   - 平缓响应

---

## 修改清单

- ✅ 修改 `judge_requirements_tool.py` 第105-129行
- ✅ 优先检查最大值，fallback到平均值
- ✅ 输出更详细的评估理由
- ✅ 两层评估逻辑一致

---

## 相关文档

- `judge_requirements_tool.py` - 需求判定工具
- `reflection_agent.py` - 反思智能体
- `optimization_workflow.py` - 优化工作流

---

## 总结

**问题**：PeakNy约束只检查平均值，忽视最大值，导致两层评估矛盾

**解决**：优先检查最大值，确保在所有工况下都满足约束

**效果**：
- ✅ 两层评估逻辑一致
- ✅ 更严格的约束检查
- ✅ 更安全的优化结果
- ✅ 避免虚假达标
