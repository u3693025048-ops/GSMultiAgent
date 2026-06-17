# T4 复跑执行说明（对照 log06082330）

本说明供执行人员在 **GSMultiAgent13 v0.4.0+** 上复现 `log06082330.txt` 同任务，验证 P0/P1 改动是否生效。

## 1. 环境准备

- 工作目录：仓库根目录 `GSMultiAgent13`
- 确认 `config.yaml` 中 `t4_low_risk.enabled: true`、`deterministic_apn: true`
- 确认 MATLAB 可用（`simulation.engine: matlab`）
- 确认 LLM API 已配置（`config.yaml` → `llm.api_key` 等）

## 2. 使用提取的 Prompt

Prompt 文件（与 log06082330 一致）：

```
prompts/prompt_log06082330.txt
```

等价命令（与原始日志相同）：

```powershell
cd E:\PythonProject\GSMultiAgent13
python cli_agent.py --file prompts/prompt_log06082330.txt 2>&1 | Tee-Object -FilePath log_t4_replay_$(Get-Date -Format 'MMddHHmm').txt
```

或使用根目录已有 `prompt.txt`（内容相同）：

```powershell
python cli_agent.py --file prompt.txt 2>&1 | Tee-Object -FilePath log_t4_replay.txt
```

## 3. 建议配置（已在 config.yaml 更新）

| 项 | 值 | 作用 |
|----|-----|------|
| `t4_low_risk.first_iter_mode` | `modify_law` | T4 首轮直接确定性 APN，跳过无效 TUNE |
| `t4_low_risk.peak_near_miss_g` | `8.0` | 20~28g 走 tune，不强制 MODIFY |
| `matlab_rl_optimizer.early_stop.patience` | `25` | 近失区延长 PPO |
| `reward_weights.hard_truncation_peak_g` | `35` | 35g 以上才硬截断 -10 |
| `constraint_local_search.borderline_select` | `true` | CLS 保留 PPO 低 peak 点 |

## 4. 日志中应出现的成功标志

执行过程中 grep / 目视检查：

1. **`[T4LowRisk] Applied deterministic minimal APN`** — Iter1/2 不再 LLM 重写 gf
2. **`[Layer2Gate] T4 MODIFY closed-loop gate`** — MODIFY 后闭环 peak 门禁
3. **无** `Mode override TUNE_PARAMS → MODIFY_LAW` 当 hit/SEP 已崩（Iter3/4 类错误）
4. **`[CLS] ... selection=borderline`** 或 CLS peak **≤ PPO best peak**（不回退到 26g）
5. Layer3 Expert 首轮 **≤3 轮**，PPO fallback 仅在 peak≤40g 且 hit≥80% 时触发

## 5. 预期对比（相对 log06082330）

| 指标 | 旧 log | 期望新 run |
|------|--------|------------|
| Iter2 PeakNy | 61.54g（LLM APN） | 不出现；deterministic APN + gate 拦截 |
| Iter3 policy | TUNE 被强制 MODIFY | 保持 TUNE（近失/多指标崩） |
| PPO Ep6 类点 | 24.82g 后 CLS 回退 | 保留 ~23g 级 PPO best |
| 最终 PeakNy_max | 26.07g（4/5） | 目标 ≤20g 或 stable borderline 复判 |

## 6. 单元测试（执行人可选）

```powershell
python -m unittest tests.test_t4_low_risk tests.test_design_path_policy tests.test_constraint_local_search -v
```

全量：

```powershell
python -m unittest discover -s tests -v
```

## 7. 运行时长

原 log 约 **7.5 小时**（4 轮外层迭代）。复跑可能更短（首轮 MODIFY、少 waste 迭代），仍建议预留 **4~8 小时**。

## 8. 结果归档

请将以下文件交给分析：

- 完整终端 log（`log_t4_replay_*.txt`）
- `guidance_output/report_latest.md`
- `guidance_output/scripts/` 下最终 `.m` 脚本
