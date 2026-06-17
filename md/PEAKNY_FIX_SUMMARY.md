# PeakNy 约束修复 - 快速总结

## 决策

采用**方案B：使用最大值（更严格）**

---

## 问题

T4工况iter6出现**两层评估矛盾**：

```
Layer 2: "PeakNy 17.23g <= 20g → 达标，跳过RL"
Reflection: "PeakNy 最大值 27.37g > 20g → 未达标，继续优化"
```

---

## 解决方案

**优先检查最大值，确保在所有工况下都满足约束**

```python
# 修复后的代码
pny_max = metrics.get("peak_ny_max", 0.0)  # 27.37g
ok = pny_max <= reqs["peak_ny_max"]        # 27.37g <= 20g → False ❌
satisfied = satisfied and ok               # 需要优化
```

---

## 修改文件

**`judge_requirements_tool.py` 第105-129行**

- 原始：仅检查平均值 `peak_ny`
- 修复：优先检查最大值 `peak_ny_max`

---

## 修复后的行为

```
iter6: 
  ├─ Layer 2: satisfied = False (PeakNy max 27.37g > 20g)
  ├─ 进入 RL 优化
  ├─ 改进参数，降低 PeakNy 最大值
  └─ 最终达标：PeakNy max ≤ 20g ✅
```

---

## 工程意义

**为什么要检查最大值？**

- 导弹需要在**所有工况**下都满足过载限制
- 极端工况虽然概率低，但一旦发生就会导致失控
- 不能因为平均值达标就忽视极端工况

---

## 预期效果

✅ 两层评估逻辑一致  
✅ 更严格的约束检查  
✅ 更安全的优化结果  
✅ 避免虚假达标  

---

## 详细说明

见 `PEAKNY_CONSTRAINT_FIX.md`
