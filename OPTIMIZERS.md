# 独立优化工具文档

本文档描述四个独立优化脚本，均可直接运行，**不依赖 Hermes Agent / LLM**，直接对 `MC_gongkuang_simulation_robust_all.m` 进行 11 维参数优化。

---

## 快速启动（开箱即用）

```bash
# PPO-RL：默认工况 A，按 config.yaml 轮次运行
python run_rl_optimize.py

# GA：默认工况 A，30 代，种群 20
python run_ga_optimize.py

# PSO：默认工况 A，50 次迭代，粒子 20
python run_pso_optimize.py

# SA：默认工况 A，100 次迭代，单解搜索
python run_sa_optimize.py
```

---

## 公共参数说明

### 优化目标：11 维参数空间

| 类别 | 参数名 | 范围 | 脚本中默认值 |
|------|--------|------|------------|
| 制导律 | `dp.N_guidance` | 2 – 5 | 3 |
| 制导律 | `dp.R_switch` | 3000 – 12000 m | 7000 |
| 制导律 | `dp.gama_max_deg` | 20 – 70 deg | 45 |
| 驾驶仪 | `dp.w1` | 5 – 25 rad/s | 14 |
| 驾驶仪 | `dp.zeta1` | 0.3 – 1.2 | 0.75 |
| 驾驶仪 | `dp.tao1` | 0.05 – 0.5 s | 0.2 |
| 驾驶仪 | `dp.w2` | 5 – 22 rad/s | 12 |
| 驾驶仪 | `dp.zeta2` | 0.3 – 1.2 | 0.75 |
| 驾驶仪 | `dp.tao2` | 0.05 – 0.5 s | 0.2 |
| 驾驶仪 | `dp.w3` | 5 – 25 rad/s | 14 |
| 驾驶仪 | `dp.zeta3` | 0.3 – 1.2 | 0.7 |

> 基线参数由脚本自动从 `--script`（或 KB 模板）中的 `dp.*` 赋值语句解析，无需手动输入。

---

### 工况条件（`--conditions` / `-c`）

工况字符串格式：`"<类别>[:<子工况列表>][;<类别>...]"`

| 类别 | 含义 | 可用子工况 |
|------|------|-----------|
| `A` | 发射角 / 俯仰扰动 | 1–6 |
| `B` | 动压 / 速度扰动 | 1–6 |
| `C` | 质量 / 惯量偏差 | 1–4 |
| `D` | 气动系数偏差 | 1–4 |
| `E` | 导引头噪声 | 1–3 |
| `F` | 综合极端工况 | 1–3 |

**示例**：

```bash
# 默认：工况 A 全部 6 个子工况
python run_rl_optimize.py

# 只跑 A 的子工况 1,2 和 B 的子工况 1
python run_rl_optimize.py --conditions "A:1,2;B:1"

# 同时覆盖 A B C 全部子工况
python run_rl_optimize.py --conditions "A;B;C"

# 全工况（A+B+C+D+E+F 全覆盖，仿真时间最长）
python run_rl_optimize.py --conditions "A;B;C;D;E;F"

# 指定具体子工况混合
python run_rl_optimize.py --conditions "A:1,2,3;B:1;C:1,2"
```

> 不指定某类别 → 该类别设为 `run_X=false`（跳过）。
> 类别字母不区分大小写。

---

### Monte Carlo 次数（`--nmc` / `-n`）

每次仿真评估内部运行的 Monte Carlo 次数，影响指标统计的置信度。

```bash
# 快速验证：每轮 5 次 MC（速度快，统计噪声大）
python run_ga_optimize.py --nmc 5

# 正常精度：10 次（推荐平衡点）
python run_ga_optimize.py --nmc 10

# 高精度：50 次（统计更准但慢）
python run_ga_optimize.py --nmc 50
```

> 不指定时使用 `config.yaml` 中 `matlab_rl_optimizer.nmc_per_eval` 的值。

---

### 指标要求（`--hitrate` / `--missmean` / `--peak-n` / `--pm`）

设定优化目标的数值要求，同时**决定运行模式**（见下节）：

| 参数 | 方向 | 单位 | 说明 |
|------|------|------|------|
| `--hitrate PCT` | ↑ 越大越好，要求下限 | % | 命中率 ≥ PCT |
| `--missmean M` | ↓ 越小越好，要求上限 | m | 脱靶量均值 ≤ M |
| `--peak-n G` | ↓ 越小越好，要求上限 | g | 峰值法向过载 ≤ G |
| `--pm DEG` | ↑ 越大越好，要求下限 | ° | 俯仰通道相位裕度 ≥ DEG |

```bash
# 只设命中率目标
python run_pso_optimize.py --hitrate 90

# 同时要求命中率 + 脱靶量 + 相位裕度
python run_pso_optimize.py --hitrate 90 --missmean 5.0 --pm 30

# 四项指标全设
python run_pso_optimize.py --hitrate 90 --missmean 5.0 --peak-n 20.0 --pm 30
```

---

### 三种运行模式（自动判断）

| 模式 | 触发条件 | 行为 |
|------|---------|------|
| **模式1 [指标驱动]** | 有指标要求 **且未**指定迭代数/代数/轮次 | Pre-优化基线满足则直接跳过；优化中每次新最优满足全部指标则**提前退出** |
| **模式2 [轮次驱动]** | **无**指标要求（无论是否指定迭代数） | 按迭代数/代数完整运行，**无提前退出** |
| **模式3 [双约束]** | 有指标要求 **且**指定了迭代数/代数/轮次 | 完整运行指定轮次，结束后**评估并打印指标达成情况（✓/✗）** |

```bash
# 模式1：满足指标就提前退出
python run_sa_optimize.py --hitrate 90 --missmean 5.0

# 模式2：无指标，跑满 100 次
python run_sa_optimize.py --iterations 100

# 模式3：跑满 100 次，结束后评估是否达标
python run_sa_optimize.py --iterations 100 --hitrate 90 --missmean 5.0
```

---

### 输出结果

- **终端**：基线指标 → 模式说明 → 每轮进度（reward / hit / miss / PeakN / PM）→ 最优 11 维参数 + 6 项最终指标
- **模式 1/3**：结束后逐项打印 ✓/✗ 评估
- **JSON 文件**：

| 算法 | 输出目录 | 文件名格式 |
|------|---------|-----------|
| RL  | `./rl_results/`  | `rl_best_YYYYMMDD_HHMMSS.json` |
| GA  | `./ga_results/`  | `ga_best_YYYYMMDD_HHMMSS.json` |
| PSO | `./pso_results/` | `pso_best_YYYYMMDD_HHMMSS.json` |
| SA  | `./sa_results/`  | `sa_best_YYYYMMDD_HHMMSS.json` |

JSON 公共字段：`algorithm` `timestamp` `script` `conditions` `mode` `requirements` `status` `elapsed_sec` `best_params` `best_metrics` `baseline_metrics`

---

## PPO 强化学习优化器（`run_rl_optimize.py`）

**算法**：近端策略优化 (PPO)，Actor-Critic 架构，11 维连续动作空间。  
**特点**：策略梯度，学习从状态到参数调整的映射；每 episode 仿真 1 次；总评估次数 = max_episodes。

### 完整参数列表

| 参数 | 简写 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `--conditions` | `-c` | str | A 全工况 | 工况字符串，见"工况条件"节 |
| `--episodes` | `-e` | int | config.yaml | 最大 RL 轮次；**指定则触发模式2/3** |
| `--nmc` | `-n` | int | config.yaml | 每轮 MC 次数 |
| `--script` | `-s` | str | KB 模板 | MATLAB 脚本路径 |
| `--hitrate` | — | float | None | 命中率目标下限 (%) |
| `--missmean` | — | float | None | 脱靶量目标上限 (m) |
| `--peak-n` | — | float | None | PeakN 目标上限 (g)，同时覆盖惩罚阈值 |
| `--pm` | — | float | None | 相位裕度目标下限 (°) |
| `--peak-n-max` | — | float | config.yaml | 奖励惩罚阈值（未设 `--peak-n` 时生效） |
| `--miss-threshold` | — | float | None | [旧参数，建议改用 `--missmean`] |

### RL 超参数（在 `config.yaml` 中修改）

```yaml
matlab_rl_optimizer:
  max_episodes: 30          # 默认最大轮次
  nmc_per_eval: 10          # 默认每轮 MC 次数
  episodes_per_update: 5    # 每隔多少 episode 更新一次策略网络
  hidden_dim: 128           # Actor/Critic 网络隐层维度
  lr_actor: 0.0003          # Actor 学习率
  lr_critic: 0.001          # Critic 学习率
  gamma: 0.99               # 折扣因子
  clip_ratio: 0.2           # PPO clip 比率
  peak_n_max: 20.0          # PeakN 奖励惩罚阈值
  peak_n_penalty: 0.5       # 超过 peak_n_max 时的惩罚系数
  reward_weights:
    hit_rate: 0.4
    miss_distance: 0.3
    pitch_PM: 0.2
    peak_n: 0.1
```

### 完整启动示例

```bash
# 最简运行（默认工况 A，按 config.yaml 轮次）
python run_rl_optimize.py

# 模式2：指定 30 轮，10 次 MC，工况 A
python run_rl_optimize.py --episodes 30 --nmc 10

# 模式1：指标驱动，满足则提前退出（最多跑 config.yaml 轮）
python run_rl_optimize.py --hitrate 90 --missmean 5.0 --pm 30

# 模式3：跑完 30 轮后评估四项指标
python run_rl_optimize.py --episodes 30 --hitrate 90 --missmean 5.0 --peak-n 20.0 --pm 30

# 指定工况 A 子工况 1,2 + B 子工况 1
python run_rl_optimize.py --conditions "A:1,2;B:1" --episodes 20 --nmc 10

# 使用自定义脚本，调整 PeakN 惩罚阈值
python run_rl_optimize.py --script ./matlab_scripts/my_script.m --peak-n-max 25.0 --episodes 50

# 指定全工况（A+B+C），高精度 MC，设全部四项指标
python run_rl_optimize.py --conditions "A;B;C" --nmc 30 \
    --hitrate 88 --missmean 6.0 --peak-n 22.0 --pm 28 --episodes 50
```

---

## 遗传算法优化器（`run_ga_optimize.py`）

**算法**：遗传算法 (GA)，种群选择-交叉-变异进化。  
**特点**：种群多样性强；每代评估 `pop_size` 次；总仿真次数 = pop_size × max_generations；精英保留 top 10%；BLX-0.5 混合交叉 + 高斯变异。

### 完整参数列表

| 参数 | 简写 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `--conditions` | `-c` | str | A 全工况 | 工况字符串 |
| `--generations` | `-g` | int | 30 | 最大代数；**指定则触发模式2/3** |
| `--nmc` | `-n` | int | config.yaml | 每代每个个体 MC 次数 |
| `--script` | `-s` | str | KB 模板 | MATLAB 脚本路径 |
| `--pop-size` | — | int | **20** | 种群大小 |
| `--crossover-rate` | — | float | **0.8** | 交叉概率（0–1） |
| `--mutation-rate` | — | float | **0.1** | 变异概率（0–1） |
| `--hitrate` | — | float | None | 命中率目标下限 (%) |
| `--missmean` | — | float | None | 脱靶量目标上限 (m) |
| `--peak-n` | — | float | None | PeakN 目标上限 (g) |
| `--pm` | — | float | None | 相位裕度目标下限 (°) |

### 超参数调优建议

| 超参数 | 偏小效果 | 偏大效果 | 推荐范围 |
|--------|---------|---------|---------|
| `--pop-size` | 多样性差，易早熟 | 每代仿真时间长 | 15–40 |
| `--crossover-rate` | 进化慢 | 过度重组破坏优质基因 | 0.7–0.9 |
| `--mutation-rate` | 停滞局部最优 | 随机游走无方向 | 0.05–0.2 |

### 完整启动示例

```bash
# 最简运行（默认参数）
python run_ga_optimize.py

# 模式2：30 代，种群 20，每个体 10 次 MC
python run_ga_optimize.py --generations 30 --nmc 10

# 模式1：指标驱动（不设代数，满足则提前退出）
python run_ga_optimize.py --hitrate 90 --missmean 5.0 --pm 30

# 模式3：严格 50 代后评估四项指标
python run_ga_optimize.py --generations 50 --hitrate 90 --missmean 5.0 --peak-n 20.0 --pm 30

# 大种群高精度（适合充裕计算资源）
python run_ga_optimize.py --generations 50 --pop-size 40 --nmc 20

# 加强探索（高交叉率 + 高变异率）
python run_ga_optimize.py --generations 40 --pop-size 30 \
    --crossover-rate 0.9 --mutation-rate 0.15 --nmc 10

# 指定工况 A+B，设指标，运行 30 代
python run_ga_optimize.py --conditions "A;B" --generations 30 \
    --hitrate 88 --missmean 6.0 --pm 28 --nmc 10
```

---

## 粒子群优化器（`run_pso_optimize.py`）

**算法**：粒子群算法 (PSO)，个体最优 (pbest) + 全局最优 (gbest) 引导速度更新。  
**特点**：收敛快；每次迭代评估 `swarm_size` 次；总仿真次数 = swarm_size × max_iterations；vmax = 20% × 参数范围防飞逸；粒子0 初始化为基线参数。

### 完整参数列表

| 参数 | 简写 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `--conditions` | `-c` | str | A 全工况 | 工况字符串 |
| `--iterations` | `-i` | int | 50 | 最大迭代次数；**指定则触发模式2/3** |
| `--nmc` | `-n` | int | config.yaml | 每次迭代每个粒子 MC 次数 |
| `--script` | `-s` | str | KB 模板 | MATLAB 脚本路径 |
| `--swarm-size` | — | int | **20** | 粒子数量 |
| `--w` | — | float | **0.7** | 惯性权重（控制粒子保持原速度的倾向） |
| `--c1` | — | float | **1.5** | 认知加速因子（pbest 拉力） |
| `--c2` | — | float | **1.5** | 社会加速因子（gbest 拉力） |
| `--hitrate` | — | float | None | 命中率目标下限 (%) |
| `--missmean` | — | float | None | 脱靶量目标上限 (m) |
| `--peak-n` | — | float | None | PeakN 目标上限 (g) |
| `--pm` | — | float | None | 相位裕度目标下限 (°) |

### 超参数调优建议

| 超参数 | 偏小效果 | 偏大效果 | 推荐范围 |
|--------|---------|---------|---------|
| `--w` | 局部开发强，收敛快 | 全局探索强，收敛慢 | 0.4–0.9 |
| `--c1` | 个体记忆弱，跟随群体 | 各自为政，多样性高 | 1.0–2.5 |
| `--c2` | 社会引导弱，全局慢 | 过度聚集，早熟收敛 | 1.0–2.5 |
| `--swarm-size` | 多样性不足 | 每轮计算量大 | 15–40 |

经典配置：`--w 0.7 --c1 1.5 --c2 1.5`（平衡）；`--w 0.9 --c1 1.2 --c2 2.0`（强社会引导）

### 完整启动示例

```bash
# 最简运行（默认参数）
python run_pso_optimize.py

# 模式2：50 次迭代，粒子 20，每粒子 10 次 MC
python run_pso_optimize.py --iterations 50 --nmc 10

# 模式1：指标驱动（不设迭代数，满足则提前退出）
python run_pso_optimize.py --hitrate 90 --missmean 5.0 --pm 30

# 模式3：严格 80 次迭代后评估四项指标
python run_pso_optimize.py --iterations 80 --hitrate 90 --missmean 5.0 --peak-n 20.0 --pm 30

# 加强全局搜索（大惯性 + 强社会引导）
python run_pso_optimize.py --iterations 80 --swarm-size 30 --w 0.9 --c1 1.2 --c2 2.0

# 加强局部精调（小惯性 + 强认知）
python run_pso_optimize.py --iterations 60 --w 0.4 --c1 2.0 --c2 1.0

# 指定工况 A+B，高 MC 精度
python run_pso_optimize.py --conditions "A;B" --iterations 50 --nmc 20 \
    --hitrate 88 --missmean 6.0 --pm 28
```

---

## 模拟退火优化器（`run_sa_optimize.py`）

**算法**：模拟退火 (SA)，单解邻域搜索，Metropolis 准则以概率接受劣解。  
**特点**：每次迭代仅 1 次仿真，计算开销最低；T(k+1) = T(k) × cooling_rate；邻域 = 高斯扰动（σ = neighbor_scale × 参数范围）；从基线参数出发。

### 完整参数列表

| 参数 | 简写 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| `--conditions` | `-c` | str | A 全工况 | 工况字符串 |
| `--iterations` | `-i` | int | 100 | 最大迭代次数；**指定则触发模式2/3** |
| `--nmc` | `-n` | int | config.yaml | 每次迭代 MC 次数 |
| `--script` | `-s` | str | KB 模板 | MATLAB 脚本路径 |
| `--t0` | — | float | **1.0** | 初始温度（越高越接受劣解，全局搜索越强） |
| `--cooling` | — | float | **0.95** | 冷却率，越接近 1 冷却越慢搜索越充分 |
| `--neighbor-scale` | — | float | **0.05** | 扰动幅度（相对参数范围比例） |
| `--hitrate` | — | float | None | 命中率目标下限 (%) |
| `--missmean` | — | float | None | 脱靶量目标上限 (m) |
| `--peak-n` | — | float | None | PeakN 目标上限 (g) |
| `--pm` | — | float | None | 相位裕度目标下限 (°) |

### 超参数调优建议

| 超参数 | 偏小效果 | 偏大效果 | 推荐范围 |
|--------|---------|---------|---------|
| `--t0` | 几乎不接受劣解，贪心搜索 | 接受大量劣解，随机游走 | 0.5–3.0 |
| `--cooling` | 冷却快，可能过早收敛 | 冷却慢，搜索充分但慢 | 0.90–0.99 |
| `--neighbor-scale` | 步长小，局部精调 | 步长大，全局跳跃 | 0.02–0.10 |

温度退火曲线：初始接受概率 ≈ `exp(-Δ/T0)`，迭代 k 次后温度 = `T0 × cooling^k`

### 完整启动示例

```bash
# 最简运行（默认参数）
python run_sa_optimize.py

# 模式2：100 次迭代，10 次 MC
python run_sa_optimize.py --iterations 100 --nmc 10

# 模式1：指标驱动（不设迭代数，满足则提前退出）
python run_sa_optimize.py --hitrate 90 --missmean 5.0 --pm 30

# 模式3：严格 200 次迭代后评估四项指标
python run_sa_optimize.py --iterations 200 --hitrate 90 --missmean 5.0 --peak-n 20.0 --pm 30

# 慢速冷却 + 大步长（强全局搜索）
python run_sa_optimize.py --iterations 200 --t0 2.0 --cooling 0.98 --neighbor-scale 0.08

# 快速精调（小步长，从当前参数细搜）
python run_sa_optimize.py --iterations 150 --t0 0.5 --cooling 0.92 --neighbor-scale 0.02

# 指定工况 A+B，高精度 MC
python run_sa_optimize.py --conditions "A;B" --iterations 150 --nmc 20 \
    --hitrate 88 --missmean 6.0 --pm 28 --t0 1.5 --cooling 0.97
```

---

## 算法对比与选型建议

| 特性 | PPO-RL | GA | PSO | SA |
|------|:------:|:--:|:---:|:--:|
| 每轮仿真次数 | 1 | pop_size (20) | swarm_size (20) | 1 |
| 典型总仿真次数 | 30–50 | 600 | 1000 | 100–200 |
| 相对计算开销 | 低 | 高 | 高 | 最低 |
| 全局搜索能力 | 中 | 强 | 中 | 强 |
| 收敛速度 | 快 | 中 | 快 | 慢 |
| 利用历史轨迹 | ✓（策略网络梯度） | ✗ | ✓（pbest） | ✗ |
| 参数敏感度 | 低（稳健） | 中 | 中 | 高 |
| 推荐场景 | 长序列持续优化 | 未知空间初始探索 | 中规模快速收敛 | 基线附近精细调整 |

**选型建议**：

- 计算资源紧张 → **SA**（每次仅 1 次仿真）
- 未知参数空间、需要广泛探索 → **GA**
- 已有较好基线、需快速收敛 → **PSO**
- 长期运行、重复任务、积累策略经验 → **PPO-RL**
- 可以串联使用：先 GA 找大致方向 → 再 SA/PSO 精调

---

## 配置文件（`config.yaml`）相关字段

以下字段影响所有优化脚本的行为，命令行参数会覆盖对应值：

```yaml
simulation:
  engine: octave              # 仿真引擎：octave 或 matlab
  octave_path: ""             # Octave 可执行文件路径（为空则使用 PATH）
  matlab_path: ""             # MATLAB 路径（engine=matlab 时使用）

matlab_rl_optimizer:
  max_episodes: 30            # RL 默认最大轮次（GA/PSO/SA 有自己的默认值）
  nmc_per_eval: 10            # 默认 Monte Carlo 次数（被 --nmc 覆盖）
  peak_n_max: 20.0            # PeakN 奖励惩罚阈值（被 --peak-n / --peak-n-max 覆盖）
  peak_n_penalty: 0.5         # PeakN 超标惩罚系数
  episodes_per_update: 5      # [仅 RL] 策略更新间隔
  hidden_dim: 128             # [仅 RL] 神经网络隐层维度
  lr_actor: 0.0003            # [仅 RL] Actor 学习率
  lr_critic: 0.001            # [仅 RL] Critic 学习率
  gamma: 0.99                 # [仅 RL] 折扣因子
  clip_ratio: 0.2             # [仅 RL] PPO clip 比率
  reward_weights:             # 奖励函数权重（所有算法共用同一评估函数）
    hit_rate: 0.4
    miss_distance: 0.3
    pitch_PM: 0.2
    peak_n: 0.1
```

---

## 公共注意事项

- 所有脚本均**不写入 `ParameterExperience`**（无跨任务记忆），每次独立运行
- 奖励/目标函数通过 `MatlabRLOptimizer._compute_reward()` 计算，四个算法完全一致，结果可横向比较
- 脚本从 `--script` 文件自动解析 `dp.*` 基线参数，基线参数作为优化起点（个体0/粒子0/初始解）
- 各脚本均读取 `config.yaml` 的仿真引擎配置，确保与 `cli_agent.py` 主流程使用相同的仿真环境
