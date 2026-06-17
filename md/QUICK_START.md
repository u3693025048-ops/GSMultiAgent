# 方案1快速参考

## 🎯 核心修改

**文件**：`multi_agent/rl/matlab_rl_optimizer.py`

### 修改1：梯度检测器类（第40-101行）
```python
class SteepGradientDetector:
    def is_steep_gradient(self):  # 检测梯度是否陡峭
    def update(self, reward, params):  # 更新历史
```

### 修改2：初始化（第2550行）
```python
steep_detector = SteepGradientDetector(window_size=5, threshold=2.0)
```

### 修改3：自适应衰减（第2557-2575行）
```python
is_steep = steep_detector.is_steep_gradient()
if is_steep:
    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.5  # 降低50%
else:
    _decay = max(0.15, 1.0 - ep / float(max_ep))  # 标准衰减
```

### 修改4：更新（第2674行）
```python
steep_detector.update(reward, new_params)
```

---

## 📊 观察指标

### ✅ 成功标志
- [ ] 日志出现"Steep gradient detected"
- [ ] decay值在梯度陡峭时降低（如0.075）
- [ ] 奖励逐步改善，不振荡
- [ ] 50-100 episode内收敛

### ❌ 失败标志
- [ ] 日志中没有"Steep gradient detected"
- [ ] 奖励在-5到-2之间反复波动
- [ ] 100 episode后仍未收敛

---

## 🔧 快速调参

```python
# 梯度检测不工作？降低阈值
steep_detector = SteepGradientDetector(window_size=5, threshold=1.5)

# 探索幅度降低太多？增大衰减因子
if is_steep:
    _decay = max(0.05, 1.0 - ep / float(max_ep)) * 0.7

# 需要更快响应？减小窗口
steep_detector = SteepGradientDetector(window_size=3, threshold=2.0)
```

---

## 📈 预期结果

| 指标 | 实施前 | 实施后 |
|------|--------|--------|
| 收敛 | ❌ 无法收敛 | ✅ 50-100 ep |
| 奖励 | 振荡 -5~-2 | 稳定改善 → +0.2 |
| 梯度检测 | 无 | 自动检测 |

---

## 🚀 运行命令

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

---

**状态**：✅ 实施完成  
**预期效果**：T4收敛
