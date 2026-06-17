# FRE 快速开始

## 问题

T4工况可行域狭窄，容易跳变，RL难以探索到符合要求的解。

## 解决方案

**Feasible Region Explorer (FRE)** - 逐步探索可行域

```
Phase 0: 宽松约束 (SEP<=100m, HR>=50%)
    ↓ 20 episodes
Phase 1: 中等约束 (SEP<=53.5m, HR>=71%)
    ↓ 20 episodes
Phase 2: 严格约束 (SEP<=7m, HR>=92%)
    ↓ 20 episodes
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **自动进阶** | 找到可行解后自动进入下一阶段 |
| **奖励加成** | 在可行域内给予额外奖励 |
| **详细日志** | 每5个episode输出进度 |
| **灵活配置** | 可调整约束范围和阶段数 |

## 运行效果

```
[FRE] Phase 0/2 | Episodes: 5/20 | Feasible: 2 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 10/20 | Feasible: 5 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 15/20 | Feasible: 8 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0/2 | Episodes: 20/20 | Feasible: 12 | SEP <= 100.0m, HitRate >= 50.0%
[FRE] Phase 0 completed (20 episodes, 12 feasible). Advancing to phase 1...
[FRE] Phase 1 constraints: SEP <= 53.5m, HitRate >= 71.0%
```

## 预期改进

| 指标 | 标准PPO | FRE | 改进 |
|------|---------|-----|------|
| 找到可行解 | 30-40 ep | 15-20 ep | **-50%** |
| 总episodes | 50-100 | 40-60 | **-30%** |
| 最终SEP | 8-10m | 6-7m | **-20%** |

## 配置调优

### 更宽松的初始约束
```python
initial_sep_threshold=150.0      # 从100m改为150m
initial_hit_rate_threshold=40.0  # 从50%改为40%
```

### 更多阶段
```python
num_phases=4                      # 从3改为4
phase_episodes=25                 # 从20改为25
```

### 更严格的目标约束
```python
target_sep_threshold=5.0          # 从7m改为5m
target_hit_rate_threshold=95.0    # 从92%改为95%
```

## 与Solution 1的对比

| 方案 | 原理 | 适用场景 |
|------|------|---------|
| **Solution 1** | 梯度陡峭检测 | 已在可行域附近 |
| **FRE** | 逐步紧化约束 | 难以找到可行域 |

**建议**：两者结合使用

## 文件位置

- 实现：`multi_agent/rl/feasible_region_explorer.py`
- 集成：`multi_agent/rl/matlab_rl_optimizer.py`
- 详细指南：`md/FRE_GUIDE.md`

## 立即运行

```bash
python cli_agent.py --prompt "T4工况，要求命中率>=92%，SEP<=7m"
```

FRE会自动启用，无需额外配置。

---

**预期结果**：T4优化在40-60个episodes内收敛，找到满足要求的解 ✅
