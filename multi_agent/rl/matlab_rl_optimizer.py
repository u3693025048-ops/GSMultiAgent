#!/usr/bin/env python3
"""
MATLAB Guidance System RL Optimizer

Dynamically extracts parameters from generated MATLAB scripts (based on the
MC_gongkuang_simulation_robust_all.m template), defines state/action spaces,
implements a guidance-specific reward function, runs PPO-style optimization,
and writes best parameters back to ParameterExperience.
"""

import re
import os
import asyncio
import copy
import json
import logging
import subprocess
import time
import math
import uuid
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np

from multi_agent.simulation.guidance_simulator import (
    OCTAVE_BATCH_FLAGS,
    DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    build_octave_eval_string,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Parameter specifications (derived from monte_carlo_single.m template)
# ─────────────────────────────────────────────────────────────────────────────

# Autopilot params: match base=struct(...,'w1',...) in monte_carlo_single.m
# RL_PARAMS block variables: rl_w1, rl_zeta1, rl_tao1, rl_w2, rl_zeta2, rl_tao2, rl_w3, rl_zeta3
AUTOPILOT_PARAM_SPECS: Dict[str, Dict[str, float]] = {
    "w1":    {"nominal": 40.0,  "min": 20.0,  "max": 60.0,  "scale": 40.0},
    "zeta1": {"nominal": 0.75,  "min": 0.30,  "max": 1.20,  "scale": 0.75},
    "tao1":  {"nominal": 0.20,  "min": 0.10,  "max": 0.40,  "scale": 0.20},
    "w2":    {"nominal": 35.0,  "min": 15.0,  "max": 55.0,  "scale": 35.0},
    "zeta2": {"nominal": 0.75,  "min": 0.30,  "max": 1.20,  "scale": 0.75},
    "tao2":  {"nominal": 0.20,  "min": 0.10,  "max": 0.40,  "scale": 0.20},
    "w3":    {"nominal": 40.0,  "min": 20.0,  "max": 60.0,  "scale": 40.0},
    "zeta3": {"nominal": 0.70,  "min": 0.30,  "max": 1.20,  "scale": 0.70},
}

# Guidance law params: rl_N_pn (navigation ratio)  [sw_dist removed — unused in gf()]
GUIDANCE_PARAM_SPECS: Dict[str, Dict[str, float]] = {
    "N_pn":  {"nominal": 4.0,  "min": 2.0,  "max": 6.0,  "scale": 4.0},
}

# Merged: RL tunes all 9 params
# (w1/zeta1/tao1 pitch  +  w2/zeta2/tao2 yaw  +  w3/zeta3 roll  +  N_pn)
ALL_TUNABLE_PARAM_SPECS: Dict[str, Dict[str, float]] = {
    **AUTOPILOT_PARAM_SPECS,
    **GUIDANCE_PARAM_SPECS,
}

# RL_PARAMS block variable name mapping (Python key → MATLAB variable name)
RL_PARAM_TO_MATLAB: Dict[str, str] = {
    "w1":    "rl_w1",
    "zeta1": "rl_zeta1",
    "tao1":  "rl_tao1",
    "w2":    "rl_w2",
    "zeta2": "rl_zeta2",
    "tao2":  "rl_tao2",
    "w3":    "rl_w3",
    "zeta3": "rl_zeta3",
    "N_pn":  "rl_N_pn",
}

PHYSICAL_PARAM_SPECS: Dict[str, Dict[str, float]] = {
    "m":  {"nominal": 231.0,  "scale": 231.0},
    "P":  {"nominal": 5000.0, "scale": 5000.0},
}

# Metrics output by monte_carlo_single: hit_rate, SEP, peak_ny, pitch_PM, pitch_BW
METRIC_SPECS: Dict[str, Dict[str, float]] = {
    "hit_rate":  {"scale": 100.0, "target": 100.0},
    "SEP":       {"scale":  20.0, "target":   0.0},
    "peak_ny":   {"scale":  20.0, "target":   8.0},
    "pitch_PM":  {"scale":  90.0, "target":  45.0},
    "pitch_BW":  {"scale":  50.0, "target":  20.0},
}

# Backward-compat aliases used by external code (e.g. reflection_agent, cli_agent)
BCKCOMPAT_METRIC_ALIASES: Dict[str, str] = {
    "miss_distance": "SEP",
    "pitch_GM":      "pitch_GM",   # GM still parsed but not in reward
    "peak_n":        "peak_ny",
}

# ── Patterns for monte_carlo_single.m print_summary / print_table output ────
# print_summary format:
#   命中率(miss<10m): 85.0%  SEP: 7.23m
#   峰值法向过载: 12.45±3.21g  max=18.67g
#   俯仰PM: 42.3±5.1°  BW: 18.5±2.3 rad/s  GM: 12.1±1.8 dB
# print_table format:
#   子工况名称   95.0%  2.34   8.12   45.2   22.5   18.3
_SIM_PARSE_PATTERNS_MC = [
    # 命中率行
    (r"命中率\(miss<[\d.]+m\):\s*([\d.]+)%",                  "hit_rate"),
    (r"SEP:\s*([\d.]+)m",                                       "SEP"),
    # 峰值法向过载行 — 取均值（第一个数字）
    (r"峰值法向过载:\s*([\d.]+)\u00b1",                          "peak_ny"),
    # 俯仰PM行
    (r"俯仰PM:\s*([\d.]+)\u00b1",                               "pitch_PM"),
    (r"BW:\s*([\d.]+)\u00b1",                                    "pitch_BW"),
    (r"GM:\s*([\d.]+)\u00b1",                                    "pitch_GM"),
    # 汇总表格行：名称  命中率%  SEP  PeakNy  PM  BW  GM
    # 匹配形如 "某工况名  88.0%  3.45  10.2  42.1  18.5  11.3"
    (r"(?:T|G|AP|R)\d[\u4e00-\u9fffA-Za-z\u00b7:：×\d]*\s+([\d.]+)%\s+([\d.]+)",
     "_table_row"),
]

# Legacy patterns for backward compatibility with old template output
_SIM_PARSE_PATTERNS_LEGACY = [
    (r"Hit\s*=\s*([-+]?\d+\.?\d*)\s*%",                     "hit_rate"),
    (r"HitRate\s*[:=]?\s*([-+]?\d+\.?\d*)\s*%",             "hit_rate"),
    (r"\bMiss\s*=\s*([-+]?\d+\.?\d*)",                       "SEP"),
    (r"miss[_\s]*dist[ance]*\s*[:=]\s*([-+]?\d+\.?\d*)",     "SEP"),
    (r"\bPM\s*=\s*([-+]?\d+\.?\d*)",                         "pitch_PM"),
    (r"\bGM\s*=\s*([-+]?\d+\.?\d*)",                         "pitch_GM"),
    (r"\bBW\s*=\s*([-+]?\d+\.?\d*)",                         "pitch_BW"),
    (r"\bPeakN\s*=\s*([-+]?\d+\.?\d*)",                      "peak_ny"),
    (r"peak[_\s]*n\s*[:=]\s*([-+]?\d+\.?\d*)",               "peak_ny"),
]


def parse_sim_stdout(raw: Any) -> Dict[str, float]:
    """Parse monte_carlo_single.m stdout into a metrics dict.

    Aggregation across multiple subcases/categories:
      - hit_rate : min  (worst-case hit rate)
      - SEP      : max  (worst-case miss distance)
      - peak_ny  : max  (worst-case peak normal load)
      - pitch_PM : min  (worst-case phase margin)
      - pitch_BW : mean (average bandwidth)
      - pitch_GM : min  (worst-case gain margin)

    Also populates legacy alias keys for backward compatibility:
      miss_distance = SEP,  peak_n = peak_ny
    """
    defaults: Dict[str, float] = {
        "hit_rate": 0.0, "SEP": 50.0, "peak_ny": 0.0,
        "pitch_PM": 30.0, "pitch_BW": 15.0, "pitch_GM": 6.0,
        # legacy aliases
        "miss_distance": 50.0, "peak_n": 0.0,
    }
    if isinstance(raw, dict):
        inner = raw.get("metrics", raw)
        for k in ("hit_rate", "SEP", "peak_ny", "pitch_PM", "pitch_BW", "pitch_GM"):
            v = inner.get(k)
            if v is not None:
                defaults[k] = float(v)
        # Legacy aliases in dict input
        for alias, target in (("miss_distance", "SEP"), ("peak_n", "peak_ny"),
                              ("pitch_BW", "pitch_BW")):
            v = inner.get(alias)
            if v is not None:
                defaults[target] = float(v)
        if "success" in inner:
            defaults["hit_rate"] = 100.0 if inner["success"] else 0.0
        defaults["miss_distance"] = defaults["SEP"]
        defaults["peak_n"] = defaults["peak_ny"]
        return defaults
    if not isinstance(raw, str) or not raw.strip():
        defaults["miss_distance"] = defaults["SEP"]
        defaults["peak_n"] = defaults["peak_ny"]
        return defaults

    # Collect all per-subcase values for aggregation
    hr_vals: List[float] = []
    sep_vals: List[float] = []
    ny_vals: List[float] = []
    pm_vals: List[float] = []
    bw_vals: List[float] = []
    gm_vals: List[float] = []

    # Parse 【汇总】block lines
    for m in re.finditer(r"命中率\(miss<[\d.]+m\):\s*([\d.]+)%", raw):
        hr_vals.append(float(m.group(1)))
    for m in re.finditer(r"SEP:\s*([\d.]+)m", raw):
        sep_vals.append(float(m.group(1)))
    for m in re.finditer(r"峰值法向过载:\s*([\d.]+)\u00b1", raw):
        ny_vals.append(float(m.group(1)))
    for m in re.finditer(r"俯仰PM:\s*([\d.]+)\u00b1", raw):
        pm_vals.append(float(m.group(1)))
    for m in re.finditer(r"BW:\s*([\d.]+)\u00b1", raw):
        bw_vals.append(float(m.group(1)))
    for m in re.finditer(r"GM:\s*([\d.]+)\u00b1", raw):
        gm_vals.append(float(m.group(1)))

    # Parse summary table rows if 【汇总】blocks absent
    if not hr_vals:
        for m in re.finditer(
            r"(?:T|G|AP|R)\d[\u4e00-\u9fffA-Za-z:\u00b7×\d]*\s+([\d.]+)%\s+([\d.]+)",
            raw,
        ):
            try:
                hr_vals.append(float(m.group(1)))
                sep_vals.append(float(m.group(2)))
            except ValueError:
                pass

    # Legacy patterns for old template output
    if not hr_vals:
        for pat, key in _SIM_PARSE_PATTERNS_LEGACY:
            matches = re.findall(pat, raw, re.IGNORECASE)
            if matches:
                try:
                    val = float(matches[-1])
                    if key == "hit_rate":  hr_vals.append(val)
                    elif key == "SEP":     sep_vals.append(val)
                    elif key == "peak_ny": ny_vals.append(val)
                    elif key == "pitch_PM":pm_vals.append(val)
                    elif key == "pitch_BW":bw_vals.append(val)
                    elif key == "pitch_GM":gm_vals.append(val)
                except ValueError:
                    pass

    # Aggregate: worst-case where applicable
    if hr_vals:  defaults["hit_rate"] = min(hr_vals)
    if sep_vals: defaults["SEP"]      = max(sep_vals)
    if ny_vals:  defaults["peak_ny"]  = max(ny_vals)
    if pm_vals:  defaults["pitch_PM"] = min(pm_vals)
    if bw_vals:  defaults["pitch_BW"] = float(sum(bw_vals) / len(bw_vals))
    if gm_vals:  defaults["pitch_GM"] = min(gm_vals)

    defaults["miss_distance"] = defaults["SEP"]
    defaults["peak_n"]        = defaults["peak_ny"]
    return defaults

# Mission categories as defined in monte_carlo_single.m
# RUN_CASE: 'T'|'G'|'AP'|'R'|'ALL'; SUB_IDX: 0=全部, 1..N=指定子工况
CATEGORY_DEFS: Dict[str, Dict] = {
    "T":  {"name": "目标机动 (Target Maneuver)",      "max_sub": 4,
           "subcases": {0:"T1:匀速直飞", 1:"T2:低频小幅度机动",
                        2:"T3:中频中等幅度机动", 3:"T4:高频大幅度机动"}},
    "G":  {"name": "交战几何 (Engagement Geometry)",  "max_sub": 5,
           "subcases": {0:"G1:标称几何", 1:"G2:近距小偏置",
                        2:"G3:近距大偏置", 3:"G4:远距小偏置", 4:"G5:远距大偏置"}},
    "AP": {"name": "驾驶仪退化 (Autopilot Degradation)","max_sub": 5,
           "subcases": {0:"AP1:全标称驾驶仪", 1:"AP2:通道时间常数单独退化",
                        2:"AP3:驾驶仪轻度退化+tao轻度退化",
                        3:"AP4:驾驶仪中度退化+tao中度退化",
                        4:"AP5:驾驶仪重度退化+tao重度退化"}},
    "R":  {"name": "综合鲁棒 (Comprehensive Robustness)","max_sub": 3,
           "subcases": {0:"R1:全标称基准", 1:"R2:多参数综合摄动",
                        2:"R3:大初始姿态偏差"}},
}


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic MATLAB Parameter Extractor
# ─────────────────────────────────────────────────────────────────────────────

def extract_matlab_params(script_content: str) -> Dict[str, float]:
    """
    Dynamically extract all numeric parameter assignments from a MATLAB script.
    Handles scalar assignments and struct.field assignments.
    All values returned as float.
    """
    params: Dict[str, float] = {}

    scalar_pat = re.compile(
        r"(?<![.\w])([a-zA-Z_]\w*)\s*=\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*;",
        re.MULTILINE,
    )
    struct_pat = re.compile(
        r"([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*=\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*;",
        re.MULTILINE,
    )

    for m in scalar_pat.finditer(script_content):
        try:
            params[m.group(1)] = float(m.group(2))
        except ValueError:
            pass

    for m in struct_pat.finditer(script_content):
        key = f"{m.group(1)}_{m.group(2)}"
        try:
            params[key] = float(m.group(3))
        except ValueError:
            pass

    return params


def extract_autopilot_params(script_content: str) -> Dict[str, float]:
    """Extract tunable parameters from RL_PARAMS block (rl_* variables) in
    monte_carlo_single-style scripts.  Falls back to scanning all scalar
    assignments if the block is absent (legacy dp.* templates)."""
    result: Dict[str, float] = {}

    # Primary: parse RL_PARAMS_BEGIN ... RL_PARAMS_END block
    rl_block_match = re.search(
        r"%%.*?RL_PARAMS_BEGIN.*?\n(.*?)%%.*?RL_PARAMS_END",
        script_content, re.DOTALL
    )
    if rl_block_match:
        block = rl_block_match.group(1)
        for py_key, ml_var in RL_PARAM_TO_MATLAB.items():
            m = re.search(
                rf"{re.escape(ml_var)}\s*=\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\s*;",
                block,
            )
            if m:
                try:
                    result[py_key] = float(m.group(1))
                except ValueError:
                    pass

    # Fallback: scan full script for dp.* or bare scalar assignments
    all_params = extract_matlab_params(script_content)
    for key, spec in ALL_TUNABLE_PARAM_SPECS.items():
        if key in result:
            continue
        dp_key = f"dp_{key}"
        if dp_key in all_params:
            result[key] = float(all_params[dp_key])
        elif key in all_params:
            result[key] = float(all_params[key])
        else:
            result[key] = float(spec["nominal"])
    return result


def extract_physical_params(script_content: str) -> Dict[str, float]:
    """Extract physical parameters (m, P) from script."""
    all_params = extract_matlab_params(script_content)
    result: Dict[str, float] = {}
    for key, spec in PHYSICAL_PARAM_SPECS.items():
        result[key] = float(all_params.get(key, spec["nominal"]))
    return result


def parse_mission_conditions(prompt: str) -> Dict[str, List[int]]:
    """
    Parse mission conditions from a prompt string for monte_carlo_single.m.

    Supported patterns
    ------------------
    * Chinese keywords: 目标机动/T, 交战几何/G, 驾驶仪/AP, 鲁棒/R、全工况
    * Explicit: ``RUN_CASE='T'; SUB_IDX=0;``
    * Legacy: ``run_T=true; sub_T=[0,1];``

    Returns
    -------
    Dict ``{category: [sub_indices]}``.  Keys are 'T','G','AP','R'.
    Empty dict means ALL categories (maps to RUN_CASE='ALL').
    If nothing is detected, defaults to ALL categories.

    Sub-indices follow CATEGORY_DEFS numbering (0-based in MATLAB
    for T0-T3, G0-G4, AP0-AP3, R0-R2).
    """
    conditions: Dict[str, List[int]] = {}

    # ── Explicit RUN_CASE='X' format ──────────────────────────────────────
    rc_match = re.search(
        r"RUN_CASE\s*=\s*['\"]([A-Za-z]+)['\"]\s*;?", prompt, re.IGNORECASE
    )
    si_match = re.search(r"SUB_IDX\s*=\s*(\d+)", prompt, re.IGNORECASE)
    if rc_match:
        rc_val = rc_match.group(1).upper()
        si_val = int(si_match.group(1)) if si_match else 0
        if rc_val == "ALL":
            return {}
        elif rc_val in CATEGORY_DEFS:
            max_s = CATEGORY_DEFS[rc_val]["max_sub"]
            conditions[rc_val] = [si_val] if si_val > 0 else list(range(0, max_s))
        return conditions

    # ── Compound-token parsing: T1/T2/G1/AP3/R2 style (highest priority) ──
    # \b(\d+)\b misses these because T and 1 share no word-boundary.
    compound_pat = re.compile(
        r"(?<![A-Za-z])(T|G|AP|R)(\d+)(?!\d)", re.IGNORECASE
    )
    for m in compound_pat.finditer(prompt):
        cat = m.group(1).upper()
        idx = int(m.group(2))
        if cat in CATEGORY_DEFS and 1 <= idx <= CATEGORY_DEFS[cat]["max_sub"]:
            conditions.setdefault(cat, [])
            if idx not in conditions[cat]:
                conditions[cat].append(idx)
    for cat in list(conditions):
        conditions[cat] = sorted(conditions[cat])
    if conditions:
        return conditions

    # ── Chinese keyword detection ────────────────────────────────────────
    kw_map = [
        ("T",  ["目标机动", "横向机动", "target maneuver", r"\bT\b"]),
        ("G",  ["交战几何", "几何工况", "engagement geometry", r"\bG\b"]),
        ("AP", ["驾驶仪", "autopilot", r"\bAP\b"]),
        ("R",  ["综合鲁棒", "鲁棒性", "robustness", r"\bR\b"]),
    ]
    all_kws = ["全工况", "所有工况", "all cases", "ALL"]
    if any(kw.lower() in prompt.lower() for kw in all_kws):
        return {}  # ALL
    for cat, kws in kw_map:
        if any(re.search(kw, prompt, re.IGNORECASE) for kw in kws):
            max_s = CATEGORY_DEFS[cat]["max_sub"]
            nums = [int(x) for x in re.findall(r"\b(\d+)\b", prompt)
                    if 1 <= int(x) <= max_s]
            conditions[cat] = sorted(set(nums)) if nums else list(range(0, max_s))

    # ── Legacy run_X = true/false format ──────────────────────────────────
    for cat in CATEGORY_DEFS:
        max_sub = CATEGORY_DEFS[cat]["max_sub"]
        run_pat = re.search(
            rf"run_{cat}\s*=\s*(true|false|\[\s*\]|1|0)\b", prompt, re.IGNORECASE
        )
        if run_pat:
            val = run_pat.group(1).lower().replace(" ", "")
            if val in ("true", "1", "[]"):
                sub_pat = re.search(rf"sub_{cat}\s*=\s*\[(.*?)\]", prompt, re.IGNORECASE)
                if sub_pat:
                    content_norm = sub_pat.group(1).strip().replace("\uff0c", ",")
                    nums = [int(x) for x in re.findall(r"\d+", content_norm)
                            if 0 <= int(x) <= max_sub]
                    conditions[cat] = sorted(set(nums)) if nums else list(range(0, max_sub))
                else:
                    conditions[cat] = list(range(0, max_sub))

    if not conditions:
        conditions["T"] = list(range(0, CATEGORY_DEFS["T"]["max_sub"]))

    return conditions


def build_matlab_conditions_str(conditions: Dict[str, List[int]]) -> str:
    """
    Convert a parsed conditions dict to MATLAB patching string for
    monte_carlo_single.m.

    Format: ``RUN_CASE='T';SUB_IDX=0;N_MC=50;``

    - Empty dict  → ``RUN_CASE='ALL';SUB_IDX=0;``
    - Single cat  → ``RUN_CASE='T';SUB_IDX=0;``  (SUB_IDX=0 = all subcases)
    - Specific sub→ ``RUN_CASE='T';SUB_IDX=1;``  (first listed subcase)
    - Multi cat   → ``RUN_CASE='ALL';SUB_IDX=0;`` (run all, filter by category)
    """
    if not conditions or len(conditions) >= len(CATEGORY_DEFS):
        return "RUN_CASE='ALL';SUB_IDX=0;"
    if len(conditions) == 1:
        cat = list(conditions.keys())[0]
        subs = conditions[cat]
        sub_idx = subs[0] if subs else 0
        return f"RUN_CASE='{cat}';SUB_IDX={sub_idx};"
    # Multiple specific categories → 'ALL' (can't express selective cats in RUN_CASE natively)
    return "RUN_CASE='ALL';SUB_IDX=0;"


class _NumpyNet:
    """Two-layer tanh network with Adam optimizer."""

    def __init__(self, in_dim: int, hid: int, out_dim: int, lr: float):
        self.lr = lr
        scale1 = math.sqrt(2.0 / in_dim)
        scale2 = math.sqrt(2.0 / hid)
        self.W1 = np.random.randn(in_dim, hid).astype(np.float32) * scale1
        self.b1 = np.zeros(hid, dtype=np.float32)
        self.W2 = np.random.randn(hid, out_dim).astype(np.float32) * scale2
        self.b2 = np.zeros(out_dim, dtype=np.float32)
        params = [self.W1, self.b1, self.W2, self.b2]
        self._m = [np.zeros_like(p) for p in params]
        self._v = [np.zeros_like(p) for p in params]
        self._t = 0

    def forward(self, x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        h = np.tanh(x @ self.W1 + self.b1)
        out = h @ self.W2 + self.b2
        return out, h

    def adam_step(self, grads: List[np.ndarray],
                  beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8) -> None:
        self._t += 1
        params = [self.W1, self.b1, self.W2, self.b2]
        for i, (p, g) in enumerate(zip(params, grads)):
            g = np.clip(g, -0.5, 0.5)
            self._m[i] = beta1 * self._m[i] + (1 - beta1) * g
            self._v[i] = beta2 * self._v[i] + (1 - beta2) * g ** 2
            mh = self._m[i] / (1 - beta1 ** self._t)
            vh = self._v[i] / (1 - beta2 ** self._t)
            p -= self.lr * mh / (np.sqrt(vh) + eps)


class ActorNet(_NumpyNet):
    """Gaussian policy: outputs action mean; fixed log_std per dimension."""

    def __init__(self, state_dim: int, action_dim: int, hid: int = 64, lr: float = 3e-4):
        super().__init__(state_dim, hid, action_dim, lr)
        self.action_dim = action_dim
        self.log_std = np.full(action_dim, -0.5, dtype=np.float32)
        self._m_ls = np.zeros(action_dim, dtype=np.float32)
        self._v_ls = np.zeros(action_dim, dtype=np.float32)

    def sample(self, state: np.ndarray, explore: bool = True
               ) -> Tuple[np.ndarray, float]:
        mean, _ = self.forward(state)
        if explore:
            std = np.exp(np.clip(self.log_std, -4.0, 2.0))
            noise = np.random.randn(self.action_dim).astype(np.float32)
            action = mean + std * noise
            lp = -0.5 * float(np.sum(noise ** 2 + 2 * self.log_std + math.log(2 * math.pi)))
        else:
            action = mean
            lp = 0.0
        return action, lp


class CriticNet(_NumpyNet):
    """State-value network V(s)."""

    def __init__(self, state_dim: int, hid: int = 64, lr: float = 1e-3):
        super().__init__(state_dim, hid, 1, lr)

    def value(self, state: np.ndarray) -> float:
        v, _ = self.forward(state)
        return float(v[0])


# ─────────────────────────────────────────────────────────────────────────────
# MATLAB script helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_matlab_function_name(content: str) -> Optional[str]:
    """
    If *content* is a MATLAB function file (first non-blank, non-comment line
    starts with 'function'), return the function name; otherwise return None.
    """
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        m = re.match(r"^function\s+(?:[^=\s]+\s*=\s*)?([a-zA-Z_]\w*)", stripped)
        if m:
            return m.group(1)
        break  # First real line is not a function declaration → script
    return None


def _looks_like_matlab_script(content: str) -> Tuple[bool, str]:
    """
    Heuristically decide whether *content* is a real MATLAB/Octave script
    rather than natural-language prose, markdown documentation, or LLM
    chatter that accidentally landed in a ``.m`` file.

    Returns ``(is_valid, reason)``.  ``reason`` is a short diagnostic
    string suitable for logging.

    A script is considered valid if it satisfies BOTH:
      • Contains at least one structural MATLAB token (``function``,
        ``clc;``, ``clear``, ``end``, ``for``/``if``/``while``).
      • Contains at least one MATLAB-style assignment with a trailing
        semicolon (``... = ...;``).

    And does NOT exhibit ANY of these red flags:
      • A heavy fraction of lines look like natural-language sentences
        (start with capital letter, end with period, no semicolons,
        no ``%`` comment marker, no MATLAB punctuation).
      • Markdown headings (``# `` at line start) or fenced code markers
        (triple-backtick blocks).
    """
    if not content or not content.strip():
        return False, "empty content"

    lines = content.splitlines()

    # Markdown / LLM-output red flags
    if any(ln.lstrip().startswith("```") for ln in lines):
        return False, "contains fenced code markers (```)"
    md_headings = sum(
        1 for ln in lines if re.match(r"^\s{0,3}#{1,6}\s+\S", ln)
    )
    if md_headings >= 2:
        return False, f"contains {md_headings} markdown headings"

    # Structural tokens — at least one must be present
    structural_re = re.compile(
        r"(^\s*function\s+\w|"
        r"^\s*clc\s*;|^\s*clear\s+|^\s*close\s+all\s*;|"
        r"^\s*end\s*$|"
        r"^\s*(for|if|while|switch)\s+\w)",
        re.MULTILINE,
    )
    has_structure = bool(structural_re.search(content))

    # MATLAB-style assignment with trailing semicolon
    assignment_re = re.compile(
        r"^\s*[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)?\s*=\s*[^=;]+;",
        re.MULTILINE,
    )
    n_assignments = len(assignment_re.findall(content))

    # Natural-language line heuristic: starts with capital letter, ends with
    # a period or Chinese full stop, has no MATLAB punctuation (=, ;, %, end,
    # etc.) on the same line.
    nat_lang_re = re.compile(
        r"^\s*[A-Z\u4e00-\u9fff][^=;%]{20,}[\.\u3002]\s*$"
    )
    n_nat_lang = sum(1 for ln in lines if nat_lang_re.match(ln))
    nat_ratio = n_nat_lang / max(1, len(lines))

    if not has_structure:
        return False, "no MATLAB structural tokens (function/clc/clear/end/…)"
    if n_assignments < 3:
        return False, (
            f"only {n_assignments} MATLAB-style assignments (… = …;) found "
            f"— expected at least 3 for a real simulation script"
        )
    if nat_ratio > 0.30:
        return False, (
            f"{nat_ratio:.0%} of lines look like natural-language prose "
            f"({n_nat_lang}/{len(lines)})"
        )

    return True, (
        f"valid (structural tokens present, {n_assignments} assignments, "
        f"natural-language ratio {nat_ratio:.0%})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Episode result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    params: Dict[str, float]
    metrics: Dict[str, float]
    reward: float
    state: np.ndarray
    action: np.ndarray
    log_prob: float
    value: float


# ─────────────────────────────────────────────────────────────────────────────
# MatlabRLOptimizer
# ─────────────────────────────────────────────────────────────────────────────

class MatlabRLOptimizer:
    """
    RL-based optimizer for guidance system parameters (autopilot + guidance law).

    Workflow
    --------
    1. Dynamically extract dp.* parameters from a generated MATLAB script.
    2. Build normalized state vector (tunable params + physical params + metrics).
    3. Action space = continuous adjustments to autopilot AND guidance law params.
    4. For each episode: sample action → update dp params → run MC simulation → compute reward.
    5. PPO-style policy gradient update every ``episodes_per_update`` steps.
    6. Write best params to ParameterExperience (long-term memory).
    """

    def __init__(
        self,
        simulator=None,
        parameter_experience=None,
        reflection_agent=None,
        hidden_dim: int = 64,
        lr_actor: float = 3e-4,
        lr_critic: float = 1e-3,
        gamma: float = 0.99,
        clip_ratio: float = 0.2,
        max_episodes: int = 50,
        episodes_per_update: int = 5,
        nmc_per_eval: int = 20,
        reflect_every: int = 1,
        peak_n_max: float = 20.0,
        peak_n_penalty: float = 1.0,
        reward_weights: Optional[Dict[str, float]] = None,
    ):
        self.simulator = simulator
        self.parameter_experience = parameter_experience
        self.reflection_agent = reflection_agent
        self.hidden_dim = hidden_dim
        self.lr_actor = lr_actor
        self.lr_critic = lr_critic
        self.gamma = gamma
        self.clip_ratio = clip_ratio
        self.max_episodes = max_episodes
        self.episodes_per_update = episodes_per_update
        self.nmc_per_eval = nmc_per_eval
        # Cadence at which the reflection agent is consulted during RL.
        # 1 = every episode (default); 2 = every other; etc. Only invoked when
        # there is a NEW best on that episode, so cost stays bounded.
        self.reflect_every = max(1, int(reflect_every))
        self._peak_n_max: float = float(peak_n_max)
        self._peak_n_penalty: float = float(peak_n_penalty)
        # Reward weights: merged from defaults + caller-supplied overrides
        _rw_defaults: Dict[str, float] = {
            # hit_rate: maximize (0~100%)
            "hit_rate": 3.0,
            # SEP: minimize (m)
            "sep_low_bonus": 2.0,   "sep_low_threshold": 2.0,
            "sep_mid_weight": 1.0,  "sep_mid_threshold": 5.0,
            # PeakNy: soft constraint (g)
            "peak_ny_max": 20.0,    "peak_ny_penalty": 1.0,
            # PM: target range [pm_min, pm_max] degrees
            "pm_bonus": 0.5,        "pm_min": 45.0,  "pm_max": 65.0,
            "pm_penalty": 0.3,
            # BW: target range [bw_min, bw_max] rad/s
            "bw_bonus": 0.2,        "bw_min": 12.0,  "bw_max": 22.0,
            "bw_penalty": 0.1,
        }
        if reward_weights:
            _rw_defaults.update(reward_weights)
        self._rw: Dict[str, float] = _rw_defaults

        self._actor: Optional[ActorNet] = None
        self._critic: Optional[CriticNet] = None
        self._action_keys: List[str] = list(ALL_TUNABLE_PARAM_SPECS.keys())
        self._state_dim: int = 0
        self._action_dim: int = len(self._action_keys)  # 8 params

        self._best_reward: float = -float("inf")
        self._best_params: Dict[str, float] = {}
        self._best_metrics: Dict[str, float] = {}
        self._best_miss_ever: float = float("inf")    # min miss across ALL episodes
        self._best_peak_n_ever: float = float("inf")  # min PeakN across ALL episodes
        self._history: List[Dict] = []

        # Stores the stderr of the last Octave/MATLAB subprocess call so that
        # _run_matlab_simulation can inspect it for syntax-error patterns and
        # decide whether to trigger a script repair pass.
        self._last_exec_stderr: str = ""
        # Optional callable: async fn(script_content, error_msg) -> fixed_content
        # Injected by cli_agent when a ModelGenerationAgent is available.
        self.script_repair_fn = None

        self._base_auto: Dict[str, float] = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        self._base_phys: Dict[str, float] = {k: float(v["nominal"]) for k, v in PHYSICAL_PARAM_SPECS.items()}
        self._last_metrics: Dict[str, float] = {k: 0.0 for k in METRIC_SPECS}

    # ── state / action helpers ────────────────────────────────────────────────

    def _build_state(
        self,
        auto: Dict[str, float],
        phys: Dict[str, float],
        metrics: Dict[str, float],
    ) -> np.ndarray:
        parts: List[float] = []
        for k in self._action_keys:
            spec = ALL_TUNABLE_PARAM_SPECS[k]
            mid = (spec["min"] + spec["max"]) / 2.0
            half = (spec["max"] - spec["min"]) / 2.0
            parts.append(float((auto.get(k, spec["nominal"]) - mid) / half))
        for k, spec in PHYSICAL_PARAM_SPECS.items():
            parts.append(float(phys.get(k, spec["nominal"]) / spec["scale"]))
        for k, spec in METRIC_SPECS.items():
            parts.append(float(metrics.get(k, 0.0) / max(spec["scale"], 1e-6)))
        return np.array(parts, dtype=np.float32)

    def _action_to_params(self, action: np.ndarray) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for i, k in enumerate(self._action_keys):
            spec = ALL_TUNABLE_PARAM_SPECS[k]
            mid = (spec["min"] + spec["max"]) / 2.0
            half = (spec["max"] - spec["min"]) / 2.0
            val = float(np.clip(mid + float(action[i]) * half, spec["min"], spec["max"]))
            result[k] = val
        return result

    # ── lightweight requirements check (no LLM) ──────────────────────────────

    @staticmethod
    def _requirements_met(metrics: Dict[str, float], reqs: Dict[str, Any]) -> bool:
        """Return True iff every non-None entry in *reqs* is satisfied by *metrics*.

        Keys: ``hitrate`` (>=), ``missmean`` (<=), ``peak_n`` (<=, only when >0),
        ``pm`` (>=).
        """
        if reqs.get("hitrate")  is not None and metrics.get("hit_rate",      0.0)           < reqs["hitrate"]:  return False
        if reqs.get("missmean") is not None and metrics.get("miss_distance", float("inf"))   > reqs["missmean"]: return False
        if reqs.get("peak_n")  is not None:
            v = metrics.get("peak_n", 0.0)
            if v > 0.0 and v > reqs["peak_n"]: return False
        if reqs.get("pm")      is not None and metrics.get("pitch_PM",      0.0)            < reqs["pm"]:       return False
        return True

    # ── reward ───────────────────────────────────────────────────────────────

    def _compute_reward(self, metrics: Dict[str, float]) -> float:
        """Reward function for monte_carlo_single.m metrics:
          - hit_rate  : maximize (higher is better)
          - SEP       : minimize (lower is better)
          - peak_ny   : minimize (soft constraint)
          - pitch_PM  : target range [pm_min, pm_max]
          - pitch_BW  : target range [bw_min, bw_max]
        """
        rw       = self._rw
        hit_rate = float(metrics.get("hit_rate", 0.0))
        sep      = float(metrics.get("SEP",      metrics.get("miss_distance", 50.0)))
        peak_ny  = float(metrics.get("peak_ny",  metrics.get("peak_n", 0.0)))
        pitch_pm = float(metrics.get("pitch_PM", 0.0))
        pitch_bw = float(metrics.get("pitch_BW", 0.0))

        reward = 0.0

        # 1. Hit rate (maximize): weight * (rate/100)
        reward += rw["hit_rate"] * (hit_rate / 100.0)

        # 2. SEP (minimize): bonus below sep_low_threshold, linear in mid range
        _sl = rw["sep_low_threshold"]
        _sm = rw["sep_mid_threshold"]
        if sep < _sl:
            reward += rw["sep_low_bonus"]
        elif sep < _sm:
            reward += rw["sep_mid_weight"] * (1.0 - (sep - _sl) / (_sm - _sl))
        else:
            reward -= min(rw["sep_low_bonus"], (sep - _sm) / _sm)

        # 3. PeakNy (soft constraint): penalty when exceeding peak_ny_max
        if peak_ny > 0.0 and rw["peak_ny_max"] > 0.0 and peak_ny > rw["peak_ny_max"]:
            overshoot = (peak_ny - rw["peak_ny_max"]) / rw["peak_ny_max"]
            reward -= rw["peak_ny_penalty"] * min(overshoot, 2.0)

        # 4. PM (target range): bonus if in [pm_min, pm_max], penalty if outside
        _pm_min = rw["pm_min"]; _pm_max = rw["pm_max"]
        if _pm_min <= pitch_pm <= _pm_max:
            reward += rw["pm_bonus"]
        else:
            dist_pm = max(_pm_min - pitch_pm, pitch_pm - _pm_max, 0.0)
            reward -= rw["pm_penalty"] * min(1.0, dist_pm / max(_pm_min, 1.0))

        # 5. BW (target range): bonus if in [bw_min, bw_max], penalty if outside
        _bw_min = rw["bw_min"]; _bw_max = rw["bw_max"]
        if _bw_min <= pitch_bw <= _bw_max:
            reward += rw["bw_bonus"]
        else:
            dist_bw = max(_bw_min - pitch_bw, pitch_bw - _bw_max, 0.0)
            reward -= rw["bw_penalty"] * min(1.0, dist_bw / max(_bw_min, 1.0))

        return float(reward)

    # ── network init ──────────────────────────────────────────────────────────

    def _init_networks(self) -> None:
        dummy = self._build_state(self._base_auto, self._base_phys, self._last_metrics)
        self._state_dim = len(dummy)
        self._actor  = ActorNet(self._state_dim, self._action_dim, self.hidden_dim, self.lr_actor)
        self._critic = CriticNet(self._state_dim, self.hidden_dim, self.lr_critic)
        logger.info(f"RL networks initialised: state_dim={self._state_dim}, action_dim={self._action_dim}")

    # ── parameter extraction from script ─────────────────────────────────────

    def extract_params_from_script(self, script_path: str) -> Dict[str, float]:
        """Load a MATLAB script and extract parameters dynamically."""
        try:
            with open(script_path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
        except FileNotFoundError:
            logger.warning(f"MATLAB script not found: {script_path}")
            return {}
        self._base_auto = extract_autopilot_params(content)
        self._base_phys = extract_physical_params(content)
        combined = {f"auto_{k}": v for k, v in self._base_auto.items()}
        combined.update({f"phys_{k}": v for k, v in self._base_phys.items()})
        logger.info(f"Extracted {len(combined)} params from {script_path}")
        return combined

    # ── simulation helpers ────────────────────────────────────────────────────

    async def _run_simulation_with_params(
        self,
        auto_params: Dict[str, float],
        mission_conditions: Optional[Dict[str, List[int]]],
        script_path: Optional[str],
        nmc: int,
    ) -> Dict[str, float]:
        if script_path and os.path.exists(script_path) and self.simulator:
            try:
                return await self._run_matlab_simulation(
                    auto_params, script_path, mission_conditions, nmc
                )
            except Exception as exc:
                logger.warning(f"MATLAB run failed ({exc}), falling back to internal sim")

        if self.simulator:
            try:
                return await self._run_internal_simulation(auto_params, mission_conditions)
            except Exception as exc:
                logger.warning(f"Internal sim failed: {exc}")

        # Last-resort analytical fallback — *still depends on auto_params* so the
        # RL gradient is non-degenerate even when no simulator is available.
        return await self._run_internal_simulation(auto_params, mission_conditions)

    @staticmethod
    def _cleanup_stale_temp_files(directory: str) -> None:
        """Remove stale RL temp files left over from a crashed previous run.

        Sweeps *directory* for files matching any of the three RL temp-file
        naming conventions (legacy ``_rl_tmp_*``, new ``rltmp_*``, function-
        style ``*_rltmp_*``).  Best-effort: silently ignores any errors so
        cleanup never blocks an RL run.
        """
        if not directory or not os.path.isdir(directory):
            return
        removed: List[str] = []
        try:
            for fname in os.listdir(directory):
                if not fname.endswith(".m"):
                    continue
                if (
                    fname.startswith("_rl_tmp")     # legacy timestamp pattern
                    or fname.startswith("rltmp_")   # new uuid pattern (plain script)
                    or "_rltmp_" in fname           # function-file pattern
                ):
                    try:
                        os.remove(os.path.join(directory, fname))
                        removed.append(fname)
                    except OSError:
                        pass
        except OSError:
            return
        if removed:
            logger.info(
                f"  [RL] Cleaned up {len(removed)} stale temp file(s) "
                f"in '{directory}': {removed[:5]}"
                f"{' …' if len(removed) > 5 else ''}"
            )

    # Compiled once at class load.  Matches a full template line that calls
    # one of the plot_* helper functions, optionally guarded by `if run_X,`.
    # Used by ``_strip_plot_calls_for_rl`` to neutralise plotting in RL.
    #
    # IMPORTANT: indent capture uses ``[ \t]*`` (horizontal whitespace only),
    # not ``\s*`` — the latter is greedy across ``\n``, so on a blank line
    # preceding ``if run_A, plot_*(…)`` the engine would erroneously anchor
    # at the blank line and consume the line break, mis-targeting the
    # substitution.
    _PLOT_CALL_RE = re.compile(
        r"^([ \t]*)(?:if\s+\w+\s*,[ \t]*)?"
        r"plot_(?:category_results|category_robust|multi_point_results|"
        r"param_scan_results|cross_category_summary|cross_category_robust)"
        r"\s*\(",
        re.MULTILINE,
    )

    # Matches lines (with optional LHS assignment) that call expensive
    # pre-analysis routines which run unconditionally before the A-F MC
    # loops and are not needed by the RL inner loop.
    # Template lines stripped:
    #   robNom      = compute_robust_metrics(960, 7000, struct(), struct());
    #   print_robust_one('Nominal ...', robNom);
    #   multiPtReport = multi_point_trajectory_analysis(nom);
    #   scanReport  = param_perturbation_scan();
    # None of these outputs feed into run_category_mc(); they are only
    # consumed by print/plot helpers that are themselves already stripped.
    _HEAVY_ANALYSIS_RE = re.compile(
        r"^([ \t]*)(?:[\w]+\s*=\s*)?"
        r"(?:"
        r"compute_robust_metrics\s*\(|"
        r"print_robust_one\s*\(|"
        r"multi_point_trajectory_analysis\s*\(|"
        r"param_perturbation_scan\s*\("
        r")",
        re.MULTILINE,
    )

    @classmethod
    def _strip_heavy_analysis_for_rl(cls, content: str) -> str:
        """Comment out heavyweight pre-analysis calls that run unconditionally
        before the A-F MC loops.  Safe to skip: their return values are only
        used by print/plot helpers (also stripped).  Typical saving: 10-16
        minutes per RL episode on a cold MATLAB in-process session."""
        spans = list(cls._HEAVY_ANALYSIS_RE.finditer(content))
        if not spans:
            return content
        new_content = content
        for m in reversed(spans):
            ls = m.start()
            le = new_content.find("\n", ls)
            if le == -1:
                le = len(new_content)
            full = new_content[ls:le]
            indent = m.group(1)
            stripped = full[len(indent):].rstrip("\r")
            new_content = (
                new_content[:ls]
                + f"{indent}% [RL skip] {stripped}"
                + new_content[le:]
            )
        logger.debug(
            f"_strip_heavy_analysis_for_rl: skipped {len(spans)} pre-analysis call(s)"
        )
        return new_content

    @classmethod
    def _strip_plot_calls_for_rl(cls, content: str) -> str:
        """Comment out top-level ``plot_*`` calls in *content* so the RL
        inner loop skips Octave figure rendering.

        The KB template ``MC_gongkuang_simulation_robust_all.m`` calls 6
        plotting helper functions after the simulation completes, each of
        which renders multiple ``figure()``s.  In a tight RL loop where we
        only need the metrics that ``print_category_summary`` already
        ``fprintf``ed (Hit, Miss, Ju, PM, GM, BW, TermAngErr), the entire
        plot phase is wasted work — typically 30+ figures per episode at
        ~200-500 ms each on Octave's Qt offscreen toolkit.

        This routine textually rewrites every line that begins (after
        optional whitespace and an optional ``if run_X,`` guard) with one
        of the six plot helper names so the line becomes an Octave comment
        starting with ``% [RL stripped]``.  ``print_category_summary``
        calls are left intact so RL metric parsing still works.

        Idempotent: a second pass adds no further changes because already
        commented lines no longer match the regex (which anchors on
        ``plot_<name>\\s*(``).
        """
        n_before = len(cls._PLOT_CALL_RE.findall(content))
        if not n_before:
            return content

        def _comment_full_line(match: "re.Match[str]") -> str:
            line_start = match.start()
            # Find the end of this line (handles \n / \r\n / EOF transparently)
            line_end = content.find("\n", line_start)
            if line_end == -1:
                line_end = len(content)
            full_line = content[line_start:line_end]
            indent = match.group(1)
            stripped = full_line[len(indent):].rstrip("\r")
            return f"{indent}% [RL stripped] {stripped}"

        # Iterative substitution because we need access to the *full* line,
        # not just the regex match span.  Walk backwards so earlier
        # substitutions don't shift later match offsets.
        spans = [m for m in cls._PLOT_CALL_RE.finditer(content)]
        new_content = content
        for m in reversed(spans):
            line_start = m.start()
            line_end   = new_content.find("\n", line_start)
            if line_end == -1:
                line_end = len(new_content)
            full_line  = new_content[line_start:line_end]
            indent     = m.group(1)
            stripped   = full_line[len(indent):].rstrip("\r")
            replacement = f"{indent}% [RL stripped] {stripped}"
            new_content = (
                new_content[:line_start] + replacement + new_content[line_end:]
            )

        logger.debug(
            f"_strip_plot_calls_for_rl: commented out {n_before} plot_* call line(s)"
        )
        return new_content

    async def _run_matlab_simulation(
        self,
        auto_params: Dict[str, float],
        script_path: str,
        mission_conditions: Optional[Dict[str, List[int]]],
        nmc: int,
    ) -> Dict[str, float]:
        with open(script_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()

        # ── Defensive content validation ────────────────────────────────────
        # If `script_path` was set incorrectly (e.g. a stale natural-language
        # ".m" file produced by a buggy upstream code path landed in the
        # matlab_scripts dir), bail out *before* writing it into a temp file
        # under our control.  This prevents the kind of bug where a temp
        # file like `_rl_tmp_<digits>.m` would be created containing
        # natural-language prose copied verbatim from a bogus source.
        is_valid, reason = _looks_like_matlab_script(content)
        if not is_valid:
            logger.error(
                f"  [RL] Refusing to run on '{script_path}': "
                f"content does not look like a MATLAB script ({reason}). "
                f"This usually means the file is LLM-generated prose, a "
                f"markdown doc, or otherwise corrupted. Falling back to "
                f"the internal Python simulator for this episode."
            )
            return await self._run_internal_simulation(auto_params, mission_conditions)
        # ────────────────────────────────────────────────────────────────────

        # ── Strategy A: patch RL_PARAMS_BEGIN block (monte_carlo_single style) ──
        rl_block_pat = re.compile(
            r"(%%.*?RL_PARAMS_BEGIN.*?\n)(.*?)(%%.*?RL_PARAMS_END)",
            re.DOTALL,
        )
        rl_block_match = rl_block_pat.search(content)
        if rl_block_match:
            block = rl_block_match.group(2)
            new_block = block
            patched_rl = []
            for py_key, ml_var in RL_PARAM_TO_MATLAB.items():
                v = auto_params.get(py_key)
                if v is None:
                    continue
                new_block, n = re.subn(
                    rf"({re.escape(ml_var)}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?(\s*;)",
                    rf"\g<1>{v:.6f}\2",
                    new_block,
                )
                if n:
                    patched_rl.append(f"{ml_var}={v:.4f}")
                else:
                    # Variable missing from block — append it
                    new_block += f"{ml_var} = {v:.6f};\n"
                    patched_rl.append(f"+{ml_var}={v:.4f}")
            content = rl_block_pat.sub(
                lambda m: m.group(1) + new_block + m.group(3), content, count=1
            )
            logger.info(f"  [RL] RL_PARAMS block patched: {patched_rl}")
        else:
            # ── Strategy B: legacy dp.* patching for old-style templates ────
            _unpatched: Dict[str, float] = {}
            for k, v in auto_params.items():
                new_content = re.sub(
                    rf"(dp\.{k}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?\s*;",
                    f"dp.{k} = {v:.6f};",
                    content,
                )
                if new_content == content:
                    _unpatched[k] = v
                else:
                    content = new_content
            if _unpatched:
                _struct_pat = re.compile(r"(dp\s*=\s*struct\s*\([^)]*\)\s*;)", re.DOTALL)
                _inject = "\n".join(f"dp.{k} = {v:.6f};" for k, v in _unpatched.items())
                content, _n = _struct_pat.subn(r"\1\n" + _inject, content, count=1)
                if not _n:
                    content = _inject + "\n" + content
                    logger.warning(f"  [RL] No dp=struct; prepended {len(_unpatched)} fields")

        # ── Patch N_MC (monte_carlo_single) or Nmc (legacy) ─────────────────
        content = re.sub(r"\bN_MC\s*=\s*\d+\s*;", f"N_MC = {nmc};", content)
        content = re.sub(r"\bNmc\s*=\s*\d+\s*;",  f"Nmc = {nmc};",  content)

        # ── Patch RUN_CASE / SUB_IDX (monte_carlo_single) ──────────────────
        if mission_conditions is not None:
            cond_str = build_matlab_conditions_str(mission_conditions)
            rc_m = re.search(r"RUN_CASE='([A-Za-z]+)';SUB_IDX=(\d+);", cond_str)
            if rc_m:
                rc_val, si_val = rc_m.group(1), rc_m.group(2)
                content = re.sub(
                    r"RUN_CASE\s*=\s*'[A-Za-z]+'",
                    f"RUN_CASE='{rc_val}'", content
                )
                content = re.sub(r"SUB_IDX\s*=\s*\d+", f"SUB_IDX={si_val}", content)
                logger.info(f"  [RL] Mission patched: RUN_CASE='{rc_val}' SUB_IDX={si_val}")

        # ── Strip plot_results call (monte_carlo_single has one call) ────────
        content = re.sub(
            r"^([ \t]*)plot_results\s*\([^;]*\)\s*;?\s*$",
            r"\1% [RL stripped] plot_results",
            content, flags=re.MULTILINE,
        )
        # Legacy: strip old-style plot_* helpers
        content = self._strip_plot_calls_for_rl(content)

        tmp_dir = os.path.dirname(os.path.abspath(script_path))

        # If the template is a *function* file, the temp file must be named after
        # the function so MATLAB/Octave can resolve it by name.  We append a
        # short uuid hex so concurrent RL workers don't clobber each other.
        unique_tag = uuid.uuid4().hex[:8]
        func_name  = _extract_matlab_function_name(content)
        if func_name:
            new_func = f"{func_name}_rltmp_{unique_tag}"
            tmp_path = os.path.join(tmp_dir, f"{new_func}.m")
            # Rename the function declaration inside to match
            content = re.sub(
                r"^function\s+" + re.escape(func_name),
                f"function {new_func}",
                content, count=1, flags=re.MULTILINE,
            )
            call_name = new_func
        else:
            # Plain script: use a basename that is itself a valid MATLAB/Octave
            # identifier (letter-prefix + hex chars, no leading underscore, no
            # all-digit suffix) so MATLAB's run() / Octave's source() never
            # mis-parse the filename as numeric or invalid identifier.
            tmp_path  = os.path.join(tmp_dir, f"rltmp_{unique_tag}.m")
            call_name = None

        # Syntax-error keywords used to distinguish parse/compile errors from
        # runtime errors (timeout, no output) so we can trigger a repair pass.
        _SYNTAX_ERR_PATTERNS = (
            "无效表达式", "invalid expression",
            "parse error", "syntax error",
            "unbalanced", "unexpected",
            "不匹配的分隔符", "mismatched",
            "此类型的变量不支持", "undefined function",
        )

        def _is_syntax_error(stderr_text: str) -> bool:
            low = stderr_text.lower()
            return any(p.lower() in low for p in _SYNTAX_ERR_PATTERNS)

        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(content)

            # ── First attempt ────────────────────────────────────────────────
            self._last_exec_stderr = ""
            stdout_text = await self._exec_matlab_subprocess(tmp_path, call_name)

            if not stdout_text:
                stderr_snap = self._last_exec_stderr
                # ── Retry path 1: re-sanitise the temp file content ──────────
                # Applies _sanitize_matlab_guidance_script to catch issues the
                # pre-write pass may have missed (e.g., from RL patching).
                if _is_syntax_error(stderr_snap):
                    logger.info(
                        "  [RL] Syntax error detected – re-sanitising script and retrying."
                    )
                    try:
                        from multi_agent.tools.simulation_tool import _sanitize_matlab_guidance_script as _san
                        fixed_content, _san_notes = _san(content)
                        if fixed_content != content:
                            content = fixed_content
                            with open(tmp_path, "w", encoding="utf-8") as fh:
                                fh.write(content)
                            stdout_text = await self._exec_matlab_subprocess(tmp_path, call_name)
                    except Exception as _san_exc:
                        logger.debug(f"  [RL] Re-sanitise failed: {_san_exc}")

                # ── Retry path 2: LLM repair via injected script_repair_fn ───
                if not stdout_text and _is_syntax_error(stderr_snap) and self.script_repair_fn:
                    logger.info(
                        "  [RL] Calling script repair agent to fix syntax error…"
                    )
                    try:
                        repaired = await self.script_repair_fn(
                            content, stderr_snap[:1500]
                        )
                        if repaired and repaired != content:
                            content = repaired
                            with open(tmp_path, "w", encoding="utf-8") as fh:
                                fh.write(content)
                            # Also update the source script file so future runs benefit
                            with open(script_path, "w", encoding="utf-8") as fh:
                                fh.write(content)
                            logger.info(
                                "  [RL] Script repaired and written back to: "
                                f"{os.path.basename(script_path)}"
                            )
                            stdout_text = await self._exec_matlab_subprocess(tmp_path, call_name)
                    except Exception as _rep_exc:
                        logger.warning(f"  [RL] Script repair failed: {_rep_exc}")

                if not stdout_text:
                    logger.warning("MATLAB subprocess produced no output; using internal fallback")
                    return await self._run_internal_simulation(auto_params, mission_conditions)

            return self._parse_sim_output(stdout_text)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    async def _exec_matlab_subprocess(self, script_path: str, call_name: Optional[str] = None) -> str:
        """
        Invoke Octave/MATLAB on *script_path* using the simulator executor's
        configured engine and capture stdout.  Returns empty string on failure.

        *call_name*: if the script is a function file, pass the function name
        so the subprocess calls it explicitly instead of using run().
        """
        executor = getattr(self.simulator, "executor", None)
        if executor is None:
            logger.warning("RL optimizer: simulator has no executor; using internal fallback")
            return ""

        engine    = getattr(executor, "engine",       "octave")
        oct_path  = getattr(executor, "octave_path",  "octave")
        mat_path  = getattr(executor, "matlab_path",  "matlab")

        script_dir  = os.path.dirname(os.path.abspath(script_path)).replace("\\", "/")
        script_abs  = os.path.abspath(script_path).replace("\\", "/")

        # ── Branch 0: in-process MATLAB Engine API for Python ──────────
        # Reuses the executor's warm matlab.engine session so we don't pay
        # the (5–15 s on Windows) MATLAB launch cost on every RL episode.
        # When the backend can't start we silently fall through to the
        # subprocess matlab branch below.
        if engine == "matlab_engine":
            backend = getattr(executor, "matlab_engine_backend", None)
            if backend is not None and backend.started:
                # run_script() is synchronous — wrap in executor to avoid
                # blocking the asyncio event loop during MATLAB execution.
                _loop = asyncio.get_event_loop()
                _tsc  = float(DEFAULT_SUBPROCESS_TIMEOUT_SEC)
                stdout, stderr, ok = await _loop.run_in_executor(
                    None,
                    lambda: backend.run_script(
                        script_abs,
                        call_name=call_name,
                        timeout_sec=_tsc,
                    ),
                )
                if ok:
                    if stdout.strip():
                        logger.debug(f"matlab.engine stdout length={len(stdout)} chars")
                        return stdout
                    # Empty stdout: MATLAB Engine API sometimes fails to
                    # capture fprintf() inside function calls on Windows.
                    # Fall through to subprocess MATLAB which reliably pipes
                    # fprintf to stdout.
                    logger.warning(
                        f"matlab.engine produced no stdout on "
                        f"'{os.path.basename(script_path)}'; "
                        f"falling through to MATLAB subprocess."
                    )
                    engine = "matlab"
                elif not backend.started:
                    # Engine crashed during run_script
                    logger.warning(
                        f"matlab.engine crashed on '{os.path.basename(script_path)}'; "
                        f"falling through to subprocess MATLAB for this episode."
                    )
                    engine = "matlab"
                else:
                    # Normal MATLAB script-level error (not a crash)
                    logger.warning(
                        f"matlab.engine script error on '{os.path.basename(script_path)}':"
                        f"\n{(stderr or '')[:2000]}"
                    )
                    return ""
            if engine == "matlab_engine":  # backend unavailable from the start
                logger.info(
                    "matlab.engine backend not started; falling back to "
                    "MATLAB subprocess for this RL call."
                )
                engine = "matlab"

        if engine == "octave":
            # source() executes the file in the current scope without
            # requiring the basename to be a valid identifier (whereas run()
            # does internal name parsing that can choke on unusual names).
            # build_octave_eval_string injects OCTAVE_BATCH_PREFIX, which
            # silences warnings, disables the pager, hides figures (no
            # rendering overhead), and pre-loads the control package.
            eval_str = build_octave_eval_string(script_abs, call_name)
            cmd = [oct_path, *OCTAVE_BATCH_FLAGS, "--eval", eval_str]
        elif engine == "matlab":
            # MATLAB equivalent: -nosplash + -nodesktop + -nodisplay strip
            # GUI init; -nojvm avoids JVM startup cost when feasible.  Note
            # MATLAB respects '-batch' but still inits graphics by default;
            # the explicit -nodisplay flag forces software offscreen mode.
            if call_name:
                eval_str = (
                    f"set(0,'DefaultFigureVisible','off'); "
                    f"addpath('{script_dir}'); {call_name}; exit"
                )
            else:
                eval_str = (
                    f"set(0,'DefaultFigureVisible','off'); "
                    f"run('{script_abs}'); exit"
                )
            cmd = [mat_path, "-nosplash", "-nodesktop", "-nodisplay",
                   "-batch", eval_str]
        else:
            logger.warning(f"Unsupported engine '{engine}' for RL optimizer")
            return ""

        # Log the exact command at debug level for reproducibility
        logger.debug(f"RL subprocess: {' '.join(repr(c) for c in cmd)}")

        try:
            _aio_proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout_b, _stderr_b = await asyncio.wait_for(
                    _aio_proc.communicate(), timeout=DEFAULT_SUBPROCESS_TIMEOUT_SEC
                )
            except asyncio.TimeoutError:
                _aio_proc.kill()
                raise subprocess.TimeoutExpired(cmd, DEFAULT_SUBPROCESS_TIMEOUT_SEC)
            _stdout = _stdout_b.decode("utf-8", errors="replace")
            _stderr = _stderr_b.decode("utf-8", errors="replace")
            stderr_excerpt = _stderr.strip()
            self._last_exec_stderr = _stderr   # always store for retry logic
            if _aio_proc.returncode != 0:
                logger.warning(
                    f"{engine} returned code {_aio_proc.returncode} on "
                    f"'{os.path.basename(script_path)}'.\n"
                    f"  cmd: {' '.join(cmd)}\n"
                    f"  stderr (up to 2000 chars):\n{stderr_excerpt[:2000]}"
                )
                return ""
            if not _stdout.strip():
                logger.warning(
                    f"{engine} produced no stdout (returncode=0) on "
                    f"'{os.path.basename(script_path)}'. "
                    f"This usually means the script ran but printed nothing "
                    f"(missing fprintf? early early-exit?).\n"
                    f"  stderr (up to 2000 chars):\n{stderr_excerpt[:2000]}"
                )
                return ""
            logger.debug(f"{engine} stdout length={len(_stdout)} chars")
            return _stdout
        except FileNotFoundError:
            logger.warning(f"{engine} executable not found; will use internal fallback")
            return ""
        except subprocess.TimeoutExpired:
            logger.warning(
                f"{engine} subprocess timed out after "
                f"{DEFAULT_SUBPROCESS_TIMEOUT_SEC}s "
                f"(set MATLAB_TIMEOUT_SEC env var to override)"
            )
            return ""
        except Exception as exc:
            logger.warning(f"{engine} subprocess failed: {exc}")
            return ""

    async def _run_internal_simulation(
        self,
        auto_params: Dict[str, float],
        mission_conditions: Optional[Dict[str, List[int]]],
    ) -> Dict[str, float]:
        """
        Lightweight Python fallback used when MATLAB/Octave is unavailable.

        Builds analytical metrics that vary smoothly with 8 tunable
        parameters (6 autopilot + 2 guidance law) so the RL signal is
        non-degenerate even without a full simulator.
        """
        # 1. Pull all tunable params with sensible defaults
        w1    = float(auto_params.get("w1",    ALL_TUNABLE_PARAM_SPECS["w1"]["nominal"]))
        zeta1 = float(auto_params.get("zeta1", ALL_TUNABLE_PARAM_SPECS["zeta1"]["nominal"]))
        w2    = float(auto_params.get("w2",    ALL_TUNABLE_PARAM_SPECS["w2"]["nominal"]))
        zeta2 = float(auto_params.get("zeta2", ALL_TUNABLE_PARAM_SPECS["zeta2"]["nominal"]))
        w3    = float(auto_params.get("w3",    ALL_TUNABLE_PARAM_SPECS["w3"]["nominal"]))
        zeta3 = float(auto_params.get("zeta3", ALL_TUNABLE_PARAM_SPECS["zeta3"]["nominal"]))
        N_pn  = float(auto_params.get("N_pn",  ALL_TUNABLE_PARAM_SPECS["N_pn"]["nominal"]))

        # 2. Try the high-level Python simulator first (varies w/ nav & damping)
        nav_coeff = N_pn
        damping   = zeta1
        try:
            study = await self.simulator.parameter_study(
                param_grid={"navigation_coefficient": [nav_coeff],
                            "damping_ratio":          [damping]},
                duration=100.0, dt=0.01,
            )
        except Exception as exc:
            logger.debug(f"parameter_study failed: {exc}")
            study = []

        # 3. Use sep_mid_threshold as analytical baseline for fallback
        rw   = self._rw
        _mm  = rw["sep_mid_threshold"]   # e.g. 5.0 m

        if study:
            m = study[0].get("metrics", {}) or {}
            base_miss = float(m.get("SEP", m.get("miss_distance", _mm)))
            base_hit  = 100.0 if m.get("success", True) else 50.0
        else:
            base_miss, base_hit = _mm, 80.0

        # Distance-from-nominal penalties (drives RL toward ALL_TUNABLE_PARAM_SPECS
        # nominal values when no real simulator is available)
        def _dev(name: str, val: float) -> float:
            spec = ALL_TUNABLE_PARAM_SPECS[name]
            half = (spec["max"] - spec["min"]) / 2.0
            return abs(val - spec["nominal"]) / max(half, 1e-6)

        tao1  = float(auto_params.get("tao1", ALL_TUNABLE_PARAM_SPECS["tao1"]["nominal"]))
        tao2  = float(auto_params.get("tao2", ALL_TUNABLE_PARAM_SPECS["tao2"]["nominal"]))
        dev_total = (_dev("w1", w1) + _dev("zeta1", zeta1) + _dev("tao1", tao1)
                   + _dev("w2", w2) + _dev("zeta2", zeta2) + _dev("tao2", tao2)
                   + _dev("w3", w3) + _dev("zeta3", zeta3)
                   + _dev("N_pn", N_pn)) / 9.0

        sep      = base_miss * (1.0 + 1.5 * dev_total)
        hit_rate = max(0.0, base_hit * (1.0 - 0.5 * dev_total))

        # Stability margins anchored to reward_weights thresholds.
        rw        = self._rw
        _pm_mid   = (rw["pm_min"] + rw["pm_max"]) / 2.0
        _pm_range = abs(rw["pm_max"] - rw["pm_min"]) / 2.0
        pitch_PM  = max(5.0, _pm_mid + _pm_range * (zeta1 - 0.5) * 2.0)

        _bw_mid  = (rw["bw_min"] + rw["bw_max"]) / 2.0
        pitch_BW = max(2.0, _bw_mid + 0.3 * (w1 + w2 + w3) / 3.0)

        return {
            "hit_rate":    float(hit_rate),
            "SEP":         float(sep),
            "miss_distance": float(sep),
            "peak_ny":     0.0,
            "peak_n":      0.0,
            "pitch_PM":    float(pitch_PM),
            "pitch_BW":    float(pitch_BW),
            "pitch_GM":    8.0,
        }

    def _parse_sim_output(self, raw: Any) -> Dict[str, float]:
        """Parse rich MATLAB stdout into the metric dict.

        Delegates to the module-level :func:`parse_sim_stdout` so both
        the RL optimizer and external callers (e.g. cli_agent) share
        identical parsing logic.
        """
        return parse_sim_stdout(raw)

    # ── PPO update ────────────────────────────────────────────────────────────

    def _ppo_update(
        self, episodes: List[EpisodeResult], old_log_probs: List[float]
    ) -> Dict[str, float]:
        if not episodes or self._actor is None or self._critic is None:
            return {}
        n = len(episodes)
        rewards = np.array([ep.reward for ep in episodes], dtype=np.float32)
        old_lp  = np.array(old_log_probs,                  dtype=np.float32)

        # Discounted returns
        returns = np.zeros(n, dtype=np.float32)
        running = 0.0
        for i in reversed(range(n)):
            running = rewards[i] + self.gamma * running
            returns[i] = running
        ret_mean, ret_std = returns.mean(), returns.std() + 1e-8
        returns_n = (returns - ret_mean) / ret_std

        values = np.array([ep.value for ep in episodes], dtype=np.float32)
        adv = returns_n - (values - ret_mean) / ret_std
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)

        a_loss_total, c_loss_total = 0.0, 0.0

        for i, ep in enumerate(episodes):
            s = ep.state
            a = ep.action

            mean_out, h_a = self._actor.forward(s)
            std = np.exp(np.clip(self._actor.log_std, -4.0, 2.0))
            noise = (a - mean_out) / (std + 1e-8)
            new_lp = float(-0.5 * np.sum(noise ** 2 + 2 * self._actor.log_std + math.log(2 * math.pi)))

            ratio = math.exp(min(max(new_lp - old_lp[i], -10.0), 10.0))
            obj1  = ratio * adv[i]
            obj2  = float(np.clip(ratio, 1 - self.clip_ratio, 1 + self.clip_ratio)) * adv[i]
            a_loss = -min(obj1, obj2)
            a_loss_total += a_loss

            d_mean = (-(a - mean_out) / (std ** 2 + 1e-8)
                      * float(np.clip(ratio, 1 - self.clip_ratio, 1 + self.clip_ratio))
                      * adv[i])
            dW2_a = np.outer(h_a, d_mean)
            db2_a = d_mean
            dh_a  = d_mean @ self._actor.W2.T
            dpre  = dh_a * (1.0 - h_a ** 2)
            dW1_a = np.outer(s, dpre)
            db1_a = dpre
            self._actor.adam_step([dW1_a, db1_a, dW2_a, db2_a])

            v_pred, h_c = self._critic.forward(s)
            v_err = float(v_pred[0]) - returns_n[i]
            c_loss_total += v_err ** 2
            dv   = np.array([2.0 * v_err], dtype=np.float32)
            dW2c = np.outer(h_c, dv)
            db2c = dv
            dhc  = dv @ self._critic.W2.T
            dprc = dhc * (1.0 - h_c ** 2)
            dW1c = np.outer(s, dprc)
            db1c = dprc
            self._critic.adam_step([dW1c, db1c, dW2c, db2c])

        return {
            "actor_loss":  float(a_loss_total / n),
            "critic_loss": float(c_loss_total / n),
        }

    # ── main optimization loop ────────────────────────────────────────────────

    async def optimize(
        self,
        script_path: Optional[str] = None,
        mission_conditions: Optional[Dict[str, List[int]]] = None,
        max_episodes: Optional[int] = None,
        nmc: Optional[int] = None,
        task_context: Optional[Dict[str, Any]] = None,
        miss_threshold: Optional[float] = None,
        task_prompt: Optional[str] = None,
        reflection_agent: Optional[Any] = None,
        reflect_every: Optional[int] = None,
        initial_auto_params: Optional[Dict[str, float]] = None,
        metric_requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Run the RL optimization loop. Early-exit is **driven solely by the
        reflection agent**: on every new best, the agent is consulted with
        the user's task prompt and the current best metrics; when it reports
        ``needs_optimization=False`` the loop exits with status
        ``"task_requirements_met"``.

        ``miss_threshold`` is no longer used as a decision criterion; if
        supplied it is forwarded to the reflection agent as additional
        numeric context only (the LLM can also read this directly from the
        prompt, so it is purely informational).

        Best parameters are persisted to ParameterExperience before returning,
        regardless of which exit path was taken.

        Returns
        -------
        dict with keys: status, best_params, best_metrics, best_reward,
        baseline_reward, total_episodes, history, reflection (if used).
        ``status`` is ``"task_requirements_met"`` on reflection-driven exit,
        otherwise ``"success"``.
        """
        max_ep = max_episodes or self.max_episodes
        n_mc   = nmc or self.nmc_per_eval

        active_reflector = reflection_agent or self.reflection_agent
        cadence = max(1, int(reflect_every) if reflect_every is not None
                      else self.reflect_every)
        reflection_enabled = bool(active_reflector and task_prompt)

        # ── Defensive cleanup of stale RL temp files ──────────────────────
        # If a previous RL run crashed before its `finally: os.remove(...)`
        # cleanup, a temp file may linger.  Sweep the script_path's directory
        # so stale files cannot be picked up as the "latest" user script.
        if script_path:
            self._cleanup_stale_temp_files(os.path.dirname(os.path.abspath(script_path)))
        # ──────────────────────────────────────────────────────────────────

        if script_path and os.path.exists(script_path):
            self.extract_params_from_script(script_path)

        # Override _base_auto with PE-retrieved params when provided.
        # This makes the baseline reflect the actual first-run / PE-cached
        # starting point rather than the MATLAB template nominal values.
        if initial_auto_params:
            for k, v in initial_auto_params.items():
                if k in ALL_TUNABLE_PARAM_SPECS:
                    spec = ALL_TUNABLE_PARAM_SPECS[k]
                    self._base_auto[k] = float(
                        np.clip(v, spec["min"], spec["max"])
                    )
            logger.info(
                f"[RL] Baseline uses PE-retrieved initial params "
                f"({len(initial_auto_params)} values)"
            )

        self._init_networks()

        logger.info("Evaluating baseline (PE-retrieved / script params)…")
        baseline_metrics = await self._run_simulation_with_params(
            self._base_auto, mission_conditions, script_path, n_mc
        )
        baseline_reward = self._compute_reward(baseline_metrics)
        logger.info(f"Baseline reward={baseline_reward:.3f}  metrics={baseline_metrics}")

        self._best_reward    = baseline_reward
        self._best_params    = copy.deepcopy(self._base_auto)
        self._best_metrics   = copy.deepcopy(baseline_metrics)
        self._best_miss_ever  = float(baseline_metrics.get("miss_distance", float("inf")))
        self._best_peak_n_ever = float(baseline_metrics.get("peak_n", float("inf")))
        self._last_metrics   = baseline_metrics

        batch: List[EpisodeResult] = []
        old_lps: List[float] = []
        final_status = "success"
        episodes_run = 0
        last_reflection: Optional[Dict[str, Any]] = None

        for ep in range(max_ep):
            episodes_run = ep + 1
            state      = self._build_state(self._base_auto, self._base_phys, self._last_metrics)
            action, lp = self._actor.sample(state, explore=True)
            value      = self._critic.value(state)
            new_params = self._action_to_params(action)

            metrics = await self._run_simulation_with_params(
                new_params, mission_conditions, script_path, n_mc
            )
            reward = self._compute_reward(metrics)

            batch.append(EpisodeResult(
                params=copy.deepcopy(new_params), metrics=copy.deepcopy(metrics),
                reward=reward, state=state, action=action, log_prob=lp, value=value,
            ))
            old_lps.append(lp)

            new_best = reward > self._best_reward
            if new_best:
                self._best_reward  = reward
                self._best_params  = copy.deepcopy(new_params)
                self._best_metrics = copy.deepcopy(metrics)
                logger.info(f"  [Ep {ep+1}] New best reward={reward:.3f}  params={new_params}")
                # Store every reward-best to SHORT_TERM for intra-session tracking
                if self.parameter_experience:
                    try:
                        from ..memory.parameter_experience import MemoryType as _MT
                        _ep_fitness = self._compute_pe_fitness(metrics)
                        await self.parameter_experience.store(
                            task_context={"task": "rl_episode_best", "episode": ep + 1,
                                          **(task_context or {})},
                            parameters={k: float(v) for k, v in new_params.items()},
                            objectives={k: float(v) for k, v in metrics.items()
                                        if isinstance(v, (int, float))},
                            fitness=_ep_fitness,
                            metadata={"episode": ep + 1, "reward": float(reward)},
                            memory_type=_MT.SHORT_TERM,
                        )
                    except Exception as _exc:
                        logger.debug(f"  [RL] Episode best SHORT_TERM store failed: {_exc}")
                # ── Lightweight requirements check (no LLM) ───────────────────────
                if metric_requirements and self._requirements_met(self._best_metrics, metric_requirements):
                    logger.info(
                        f"  [RL] All metric requirements met at episode {ep+1}; early exit."
                    )
                    final_status = "requirements_met"
                    break
            # Track best miss and peak_n independently of reward
            cur_miss   = float(metrics.get("miss_distance", float("inf")))
            cur_peak_n = float(metrics.get("peak_n", float("inf")))
            if cur_miss < self._best_miss_ever:
                self._best_miss_ever = cur_miss
            if cur_peak_n < self._best_peak_n_ever:
                self._best_peak_n_ever = cur_peak_n

            self._last_metrics = metrics
            self._history.append({
                "episode": ep + 1, "reward": reward,
                "metrics": metrics, "params": new_params,
            })

            best_reward_miss = float(self._best_metrics.get("miss_distance", 99.0))
            _peak_n_str = f"{metrics.get('peak_n', 0.0):.2f}" if metrics.get('peak_n', 0.0) > 0 else "N/A"
            logger.info(
                f"  [Ep {ep+1}/{max_ep}] reward={reward:.3f}  "
                f"hit={metrics.get('hit_rate',0):.1f}%  "
                f"miss={metrics.get('miss_distance',99):.2f}m  "
                f"best_reward_miss={best_reward_miss:.2f}m  "
                f"best_miss_ever={self._best_miss_ever:.2f}m  "
                f"PeakN={_peak_n_str}  "
                f"PM={metrics.get('pitch_PM',0):.1f}°"
            )

            # ── Reflection-based task-requirement check (sole early-exit) ─────────
            if (reflection_enabled
                    and ((ep + 1) % cadence == 0)):
                try:
                    reflection_input = {
                        "parameters":          self._best_params,
                        "metrics":             metrics,
                        "best_reward_metrics": self._best_metrics,
                        "best_miss_ever":      self._best_miss_ever,
                        "best_peak_n_ever":    self._best_peak_n_ever,
                        "episode":             ep + 1,
                        "new_best":            new_best,
                        "best_reward":         float(self._best_reward),
                    }
                    if miss_threshold is not None:
                        reflection_input["miss_threshold_hint"] = float(miss_threshold)
                    reflection = await active_reflector.reflect(
                        task_prompt, reflection_input
                    )
                    last_reflection = reflection
                    needs_more = bool(reflection.get("needs_optimization", True))
                    suggestion = reflection.get("suggestion", "")
                    logger.info(
                        f"  [RL Reflection @ Ep {ep+1}] needs_optimization="
                        f"{needs_more} | {suggestion[:120]}"
                    )
                    if not needs_more:
                        logger.info(
                            f"  [RL] Task requirements met per reflection at "
                            f"episode {ep+1}; early exit."
                        )
                        final_status = "task_requirements_met"
                        break
                    _MODIFY_SIGNALS = [
                        "制导律", "算法结构", "modify_law", "修改制导律", "新的制导",
                        "重新设计", "滑模", "预测制导", "guidance law", "algorithm",
                    ]
                    if any(sig in suggestion.lower() for sig in _MODIFY_SIGNALS):
                        logger.info(
                            f"  [RL] Reflection suggests design-path change at "
                            f"episode {ep+1}; breaking to let Hermes re-plan. "
                            f"Hint: {suggestion[:200]}"
                        )
                        final_status = "needs_design_path_change"
                        break
                except Exception as ref_exc:
                    logger.warning(f"  [RL] Reflection call failed: {ref_exc}")
            # ──────────────────────────────────────────────────────────────

            if len(batch) >= self.episodes_per_update:
                loss = self._ppo_update(batch, old_lps)
                logger.info(f"  [Update] actor_loss={loss.get('actor_loss',0):.4f}  "
                            f"critic_loss={loss.get('critic_loss',0):.4f}")
                batch.clear()
                old_lps.clear()

        if batch:
            self._ppo_update(batch, old_lps)

        if self.parameter_experience and self._best_params:
            await self._store_best_params(task_context or {}, final_status=final_status)

        return {
            "status":          final_status,
            "best_params":     self._best_params,
            "best_metrics":    self._best_metrics,
            "best_reward":     self._best_reward,
            "baseline_reward": baseline_reward,
            "total_episodes":  episodes_run,
            "history":         self._history[-10:],
            "reflection":      last_reflection,
        }

    def _compute_pe_fitness(self, metrics: Dict[str, float]) -> float:
        """
        四指标综合适应度，用于 ParameterExperience 存储与检索排序。
        权重: hit_rate(↑)×0.40 + miss_distance(↓)×0.30 + pitch_PM(↑)×0.20 + peak_n(↓)×0.10
        返回值在 [0, 1] 之间，越大越好。当 peak_n 无有效值（≤0）时按 0.5 中性处理。
        """
        hit    = float(metrics.get("hit_rate",      0.0))
        miss   = float(metrics.get("miss_distance", 100.0))
        pm     = float(metrics.get("pitch_PM",       0.0))
        peak_n = float(metrics.get("peak_n",         0.0))
        pn_ref = max(1.0, float(self._peak_n_max))

        hit_score    = hit / 100.0
        miss_score   = 1.0 / (1.0 + miss)
        pm_score     = min(max(pm, 0.0), 90.0) / 90.0
        peak_n_score = 1.0 / (1.0 + max(0.0, peak_n) / pn_ref) if peak_n > 0 else 0.5

        return max(0.0, min(1.0,
            0.4 * hit_score + 0.3 * miss_score + 0.2 * pm_score + 0.1 * peak_n_score
        ))

    async def _store_best_params(self, task_context: Dict[str, Any], final_status: str = "success") -> None:
        """Persist best params to ParameterExperience.

        Memory layer strategy:
        - ``task_requirements_met`` → LONG_TERM (reflection-validated, cross-session)
        - ``success``               → SHORT_TERM (completed, pending auto_promote)
        """
        from ..memory.parameter_experience import MemoryType

        combined = {f"dp_{k}": float(v) for k, v in self._best_params.items()}
        combined.update({f"phys_{k}": float(v) for k, v in self._base_phys.items()})

        objectives = {
            "hit_rate":       float(self._best_metrics.get("hit_rate",       0.0)),
            "miss_distance":  float(self._best_metrics.get("miss_distance",  100.0)),
            "control_energy": float(self._best_metrics.get("control_energy", 50.0)),
            "pitch_PM":       float(self._best_metrics.get("pitch_PM",       0.0)),
            "pitch_GM":       float(self._best_metrics.get("pitch_GM",       0.0)),
            "peak_n":         float(self._best_metrics.get("peak_n",         0.0)),
        }

        fitness = self._compute_pe_fitness(self._best_metrics)

        ctx = {"task": "guidance_rl_optimization", "algorithm": "PPO",
               "best_reward": float(self._best_reward), **task_context}

        # Split best_params into guidance vs autopilot groups for metadata
        guidance_best  = {k: float(v) for k, v in self._best_params.items() if k in GUIDANCE_PARAM_SPECS}
        autopilot_best = {k: float(v) for k, v in self._best_params.items() if k in AUTOPILOT_PARAM_SPECS}

        target_type = (
            MemoryType.LONG_TERM
            if final_status == "task_requirements_met"
            else MemoryType.SHORT_TERM
        )
        mem_id = await self.parameter_experience.store(
            task_context=ctx,
            parameters=combined,
            objectives=objectives,
            fitness=fitness,
            metadata={
                "optimizer":       "MatlabRLOptimizer",
                "episode_count":   len(self._history),
                "timestamp":       time.time(),
                "final_status":    final_status,
                "guidance_params": guidance_best,
                "autopilot_params": autopilot_best,
            },
            memory_type=target_type,
        )
        logger.info(
            f"Best params stored → memory_id={mem_id}, fitness={fitness:.4f}, "
            f"layer={'LONG_TERM' if target_type == MemoryType.LONG_TERM else 'SHORT_TERM'} | "
            f"guidance={guidance_best} | autopilot_w1={autopilot_best.get('w1')}"
        )

    def get_statistics(self) -> Dict[str, Any]:
        if not self._history:
            return {"status": "not_started"}
        rewards = [ep["reward"] for ep in self._history]
        return {
            "total_episodes":     len(self._history),
            "best_reward":        self._best_reward,
            "best_params":        self._best_params,
            "best_metrics":       self._best_metrics,
            "mean_reward_last10": float(np.mean(rewards[-10:])),
            "reward_trend":       rewards[-20:],
        }
