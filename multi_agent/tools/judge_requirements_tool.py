#!/usr/bin/env python3
"""
JudgeRequirementsTool - Layer 2 Hermes tool.

Called immediately after run_simulation completes.
Evaluates whether the simulation metrics satisfy the task requirements
extracted from the user natural language prompt.

Decision logic (two-stage):
  Stage 1 - Rule-based fast check (hit_rate/SEP/peak_ny/PM/BW thresholds).
  Stage 2 - LLM judgment via ReflectionAgent (when Stage 1 passes or is close).

Returns JSON: {satisfied, reason, metrics_summary, next_step}
  next_step: "done" -> Layer3 reflection | "rl_optimize" -> Layer3 RL
"""

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _parse_requirements_from_prompt(prompt: str) -> Dict[str, Any]:
    """Extract numeric requirements from natural language prompt."""
    reqs: Dict[str, Any] = {}

    for pat in [
        r"命中率\s*[>=]+\s*(\d+(?:\.\d+)?)\s*%",
        r"hit[_\s]*rate\s*[>=]+\s*(\d+(?:\.\d+)?)",
    ]:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            reqs["hit_rate_min"] = float(m.group(1))
            break

    for pat in [
        r"(?:脱靶量|SEP|miss)\s*[<=]+\s*(\d+(?:\.\d+)?)\s*m",
        r"miss\s*distance\s*[<=]+\s*(\d+(?:\.\d+)?)",
    ]:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            reqs["sep_max"] = float(m.group(1))
            break

    m = re.search(
        r"(?:峰值法向过载|法向过载|PeakNy|peak_ny)\s*[<=]+\s*(\d+(?:\.\d+)?)\s*g",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["peak_ny_max"] = float(m.group(1))

    m = re.search(
        r"PM\s*(?:在|in|∈)\s*\[?\s*(\d+(?:\.\d+)?)\s*[,~到\-]\s*(\d+(?:\.\d+)?)",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["pm_min"] = float(m.group(1))
        reqs["pm_max"] = float(m.group(2))
    else:
        for pat in [
            r"PM\s*[>=]+\s*(\d+(?:\.\d+)?)\s*°?",
            r"相位裕度\s*[>=]+\s*(\d+(?:\.\d+)?)",
        ]:
            m = re.search(pat, prompt, re.IGNORECASE)
            if m:
                reqs["pm_min"] = float(m.group(1))
                break

    m = re.search(
        r"BW\s*(?:在|in)\s*\[?\s*(\d+(?:\.\d+)?)\s*[,~到]\s*(\d+(?:\.\d+)?)",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["bw_min"] = float(m.group(1))
        reqs["bw_max"] = float(m.group(2))

    return reqs


def _rule_check(metrics: Dict[str, float], reqs: Dict[str, Any]) -> tuple:
    """Returns (satisfied: bool, reasons: list[str])."""
    reasons = []
    satisfied = True

    if "hit_rate_min" in reqs:
        hr = metrics.get("hit_rate", 0.0)
        ok = hr >= reqs["hit_rate_min"]
        satisfied = satisfied and ok
        reasons.append(
            f"命中率 {hr:.1f}% {'>=' if ok else '<'} 要求 {reqs['hit_rate_min']:.1f}%"
            + (" [OK]" if ok else " [NG]")
        )

    if "sep_max" in reqs:
        sep = metrics.get("SEP", metrics.get("miss_distance", 999.0))
        ok = sep <= reqs["sep_max"]
        satisfied = satisfied and ok
        reasons.append(
            f"SEP {sep:.2f}m {'<=' if ok else '>'} 要求 {reqs['sep_max']:.2f}m"
            + (" [OK]" if ok else " [NG]")
        )

    if "peak_ny_max" in reqs:
        pny = metrics.get("peak_ny", metrics.get("peak_n", 0.0))
        if pny <= 0.0:
            reasons.append("PeakNy 数据不可用（跳过此约束）")
        else:
            ok = pny <= reqs["peak_ny_max"]
            satisfied = satisfied and ok
            reasons.append(
                f"PeakNy {pny:.2f}g {'<=' if ok else '>'} 要求 {reqs['peak_ny_max']:.2f}g"
                + (" [OK]" if ok else " [NG]")
            )

    if "pm_min" in reqs:
        pm = metrics.get("pitch_PM", 0.0)
        if "pm_max" in reqs:
            ok = reqs["pm_min"] <= pm <= reqs["pm_max"]
            satisfied = satisfied and ok
            reasons.append(
                f"PM {pm:.1f}deg 在 [{reqs['pm_min']:.1f}, {reqs['pm_max']:.1f}]"
                + (" [OK]" if ok else " [NG]")
            )
        else:
            ok = pm >= reqs["pm_min"]
            satisfied = satisfied and ok
            reasons.append(
                f"PM {pm:.1f}deg {'>=' if ok else '<'} 要求 {reqs['pm_min']:.1f}deg"
                + (" [OK]" if ok else " [NG]")
            )

    if "bw_min" in reqs and "bw_max" in reqs:
        bw = metrics.get("pitch_BW", 0.0)
        ok = reqs["bw_min"] <= bw <= reqs["bw_max"]
        satisfied = satisfied and ok
        reasons.append(
            f"BW {bw:.1f} rad/s 在 [{reqs['bw_min']},{reqs['bw_max']}]"
            + (" [OK]" if ok else " [NG]")
        )

    return satisfied, reasons


class JudgeRequirementsTool:

    name = "judge_requirements"

    description = (
        "判断仿真结果是否满足任务指标要求。"
        "输入任务描述和仿真指标（hit_rate/SEP/peak_ny/pitch_PM/pitch_BW），"
        "返回 {satisfied, reason, next_step}。"
        "next_step='done' 表示可跳过 RL 直接进入反思智能体；"
        "'rl_optimize' 表示需要 RL 参数优化。"
    )

    input_schema = {
        "type": "object",
        "properties": {
            "task_prompt": {
                "type": "string",
                "description": "用户任务描述（含指标要求）",
            },
            "metrics": {
                "type": "object",
                "description": "仿真指标字典，键: hit_rate, SEP, peak_ny, pitch_PM, pitch_BW",
            },
            "script_path": {
                "type": "string",
                "description": "（可选）仿真脚本路径，用于标识本次结果",
            },
        },
        "required": ["task_prompt", "metrics"],
    }

    def __init__(self):
        self._reflection_agent = None
        self._task_prompt_cache: str = ""
        self._last_result: Optional[Dict[str, Any]] = None

    def set_reflection_agent(self, agent: Any) -> None:
        self._reflection_agent = agent

    def set_task_prompt(self, prompt: str) -> None:
        self._task_prompt_cache = prompt

    async def execute(
        self,
        task_prompt: str = "",
        metrics: Optional[Dict[str, Any]] = None,
        script_path: str = "",
    ) -> str:
        if not task_prompt:
            task_prompt = self._task_prompt_cache
        if metrics is None:
            metrics = {}

        m: Dict[str, float] = {}
        for k, v in metrics.items():
            try:
                m[k] = float(v)
            except (TypeError, ValueError):
                pass

        reqs = _parse_requirements_from_prompt(task_prompt)
        if reqs:
            satisfied, reasons = _rule_check(m, reqs)
            reason_str = "; ".join(reasons) if reasons else "规则检查通过"
        else:
            satisfied = False
            reason_str = "未检测到明确数值要求，将转入 RL 优化"

        if self._reflection_agent is not None and reqs and task_prompt:
            try:
                ref = await self._reflection_agent.reflect(task_prompt, {"metrics": m})
                llm_satisfied = not ref.get("needs_optimization", True)
                llm_suggestion = ref.get("suggestion", "")
                if llm_satisfied and not satisfied:
                    satisfied = True
                    reason_str += f"; LLM判断: {llm_suggestion[:200]}"
                elif not llm_satisfied and satisfied:
                    satisfied = False
                    reason_str += f"; LLM判断需改进: {llm_suggestion[:200]}"
            except Exception as exc:
                logger.warning(f"JudgeRequirements LLM stage failed: {exc}")

        summary = {
            "命中率(%)": m.get("hit_rate", 0.0),
            "SEP(m)": m.get("SEP", m.get("miss_distance", 0.0)),
            "PeakNy(g)": m.get("peak_ny", m.get("peak_n", 0.0)),
            "PM(deg)": m.get("pitch_PM", 0.0),
            "BW(r/s)": m.get("pitch_BW", 0.0),
        }

        result = {
            "satisfied": satisfied,
            "reason": reason_str,
            "metrics_summary": summary,
            "next_step": "done" if satisfied else "rl_optimize",
            "requirements_found": reqs,
        }
        self._last_result = result
        logger.info(f"[JudgeRequirements] satisfied={satisfied} | {reason_str[:120]}")
        return json.dumps(result, ensure_ascii=False)
