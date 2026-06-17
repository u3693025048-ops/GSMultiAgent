# Expert模式增强 - 快速参考

## 三层分析

```
仿真结果分析 → 仿真文件分析 → 参数调优建议 → 执行调整
```

## ExpertAnalyzer 核心方法

### 1. 分析仿真文件
```python
file_analysis = await analyzer.analyze_simulation_file(
    script_path=script_path,
    task_prompt=task_prompt,
    current_metrics=current_metrics,
)
# 返回: file_analysis, issues, suggestions
```

### 2. 生成调优建议
```python
tuning = await analyzer.generate_tuning_suggestions(
    current_metrics=current_metrics,
    task_prompt=task_prompt,
    file_analysis=file_analysis,
    optimization_history=optimization_history,
)
# 返回: param_suggestions, tuning_strategy, priority
```

## 参数效应速查表

| 参数 | 效应 | 范围 | 安全值 |
|------|------|------|--------|
| w1 | BW↑, PM↓ | [20,60] | [30,50] |
| zeta1 | PM↑ | [0.3,1.5] | [0.6,1.0] |
| tao1 | PM↓↓ | [0.05,0.6] | [0.08,0.20] |
| N_pn | hit↑, SEP↓, Ny↑ | [2,6] | [3,5] |

## 调优策略速查

| 问题 | 优先调整 | 方向 |
|------|---------|------|
| 命中率不足 | N_pn, w1 | ↑ |
| SEP过大 | w2, zeta2, N_pn | ↑ |
| PeakNy过大 | w3, zeta3, N_pn | ↓ |
| PM过低 | tao1, zeta1, w1 | ↓↑↓ |
| BW超范围 | w1 | 调整到目标 |

## 集成步骤

1. **初始化分析器**
   ```python
   analyzer = ExpertAnalyzer(llm_client=hermes.agent)
   ```

2. **分析仿真文件**
   ```python
   file_analysis = await analyzer.analyze_simulation_file(...)
   ```

3. **生成调优建议**
   ```python
   tuning = await analyzer.generate_tuning_suggestions(...)
   ```

4. **应用建议并仿真**
   ```python
   new_metrics = await rl_optimizer._run_simulation_with_params(...)
   ```

## 日志示例

```
[ExpertAnalyzer] 分析仿真文件...
[ExpertAnalyzer] 文件分析完成: 发现3个问题
[ExpertAnalyzer] 生成调优建议...
[ExpertAnalyzer] 调优建议完成: 优先级 [w1, zeta1, N_pn]
```

## 配置

```yaml
matlab_rl_optimizer:
  layer3_strategy: "expert"
  expert_max_rounds: 5
  expert_nmc: 30
```

## 关键特性

✅ 自动分析仿真文件代码  
✅ 识别代码中的潜在问题  
✅ 生成具体的参数调优建议  
✅ 提供调优优先级指导  
✅ 提高调优效率 20-30%  

## 详细说明

见 `EXPERT_MODE_ENHANCED.md`
