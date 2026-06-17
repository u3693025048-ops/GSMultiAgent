# 方案1快速参考卡

## 🎯 一句话总结

**在梯度陡峭区域自动降低PPO探索幅度，避免冲坏T4的窄可行域**

---

## 📝 修改清单

### 文件：`multi_agent/rl/matlab_rl_optimizer.py`

#### 修改1：添加梯度检测器类（第36-101行）
```python
class SteepGradientDetector:
    def __init__(self, window_size=5, threshold=2.0):
        self.window_size = window_size
        self.threshold = threshold
        self.reward_history = []
        self.param_history = []
    
    def is_steep_gradient(self):
        # 计算梯度 = 奖励变化 / 参数变化
        # 返回是否 > threshold
    
    def update(self, reward, params):
        # 更新历史记录
```

#### 修改2：初始化检测器（第2549-2550行）
```python
steep_detector = SteepGradientDetector(window_size=5, threshold=2.0)
```

#### 修改3：自适应探索衰减（第2556-2575行）
```python
is_steep = steep_detector.is_steep_gradient()

if is_steep:
    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.5
    logger.info(f"  [Ep {ep+1}] Steep gradient detected, reducing exploration (decay={_decay:.3f})")
else:
    _decay = max(0.15, 1.0 - ep / float(max_ep))
```

#### 修改4：更新检测器（第2673-2674行）
```python
steep_detector.update(reward, new_params)
```

---

## ✅ 验证

```bash
python -m py_compile multi_agent/rl/matlab_rl_optimizer.py
```

**预期**：无错误输出

---

## 🚀 运行

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

## 📊 观察指标

### 成功标志 ✅

- [ ] 日志出现"Steep gradient detected"
- [ ] decay值在梯度陡峭时降低（如0.075）
- [ ] 奖励逐步改善，不振荡
- [ ] 50-100 episode内收敛

### 失败标志 ❌

- [ ] 日志中没有"Steep gradient detected"
- [ ] 奖励在-5到-2之间反复波动
- [ ] 100 episode后仍未收敛

---

## 🔧 快速调参

### 梯度检测不工作？

```python
# 降低阈值
steep_detector = SteepGradientDetector(window_size=5, threshold=1.5)
```

### 探索幅度降低太多？

```python
# 增大衰减因子
if is_steep:
    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.7
```

### 需要更快响应？

```python
# 减小窗口
steep_detector = SteepGradientDetector(window_size=3, threshold=2.0)
```

---

## 📈 预期结果

| 指标 | 实施前 | 实施后 |
|------|--------|--------|
| 收敛 | ❌ 无法收敛 | ✅ 50-100 ep |
| 奖励 | 振荡 -5~-2 | 稳定改善 → +0.2 |
| 梯度检测 | 无 | 自动检测 |
| 日志 | 无梯度消息 | 有梯度消息 |

---

## 📚 文档导航

- **详细指南**：`STEEP_GRADIENT_FIX.md`
- **技术细节**：`T4_NARROW_FEASIBLE_REGION.md`
- **完整总结**：`T4_FEASIBLE_REGION_SUMMARY.md`
- **测试计划**：`TEST_PLAN.md`
- **实施报告**：`IMPLEMENTATION_COMPLETE.md`

---

## 💡 核心原理

```
梯度陡峭 = 参数变化小 → 奖励变化大

解决方案：
├─ 检测梯度陡峭
├─ 自动降低探索幅度（×0.5）
└─ 在可行域附近精细搜索
```

---

## 🎯 下一步

1. **验证**：`python -m py_compile ...`
2. **运行**：`python cli_agent.py --prompt "T4工况..."`
3. **观察**：看日志中是否出现梯度检测消息
4. **评估**：检查是否在50-100 episode内收敛

---

**状态**：✅ 实施完成  
**风险**：低  
**预期效果**：T4收敛
