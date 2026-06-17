# 快速修复：PeakNy 超标问题

## 问题

第一轮 RL 优化结果中，**PeakNy=25.27g 超出 20g 要求**，其他指标都达标。

## 根本原因

奖励函数中 PeakNy 的惩罚权重太低（`peak_ny_penalty: 1.0`），RL 没有充分激励去优化这个指标。

## 快速修复（1 分钟）

### 步骤 1：打开配置文件

编辑 `config.yaml`，找到这一行（约第 330 行）：

```yaml
peak_n_penalty: 1.0
```

### 步骤 2：修改为

```yaml
peak_n_penalty: 2.0  # 翻倍
```

### 步骤 3：保存并重新运行

```bash
python cli_agent.py --prompt "你的任务提示"
```

## 预期结果

```
修改前：PeakNy=25.27g ✗
修改后：PeakNy=20-22g ✓

改善幅度：15-20% 下降
运行时间：不增加（仍是 12 分钟）
```

## 如果还不够

如果修改后 PeakNy 仍未达标，继续调整：

```yaml
peak_n_penalty: 3.0  # 继续增大
max_episodes: 75     # 增加 episode（可选）
```

## 为什么这样做？

- **PeakNy 是软约束**：不像 hit_rate 和 SEP 那样直接影响任务成功
- **权重太低**：RL 优先优化高权重指标，低权重指标被忽视
- **增大权重**：RL 会更积极地优化 PeakNy

## 详细说明

查看 `RL_OPTIMIZATION_TUNING.md` 了解：
- 完整的调参原理
- 多种调参方案
- 监控指标和验证方法
- 常见问题解答

---

**立即行动**：修改 `config.yaml` 中的 `peak_n_penalty: 1.0 → 2.0`，然后重新运行。
