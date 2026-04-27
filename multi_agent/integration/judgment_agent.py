#!/usr/bin/env python3
"""
JudgmentAgent — Layer 3 per-episode judgment component.

Called by MatlabRLOptimizer after each episode when a new best is found.
Provides lightweight real-time evaluation of whether RL optimization can
stop early (requirements already met).

Three-level judgment:
  Level 0 - LLM requirement extraction (once, on first call):
    Parses task prompt via LLM to extract numeric thresholds.
    Falls back to regex if LLM unavailable or fails.
  Level 1 - Numeric rule check (fast, no LLM):
    Uses parsed task requirements for hard threshold checks.
  Level 2 - ReflectionAgent consultation (only when Level 1 passes):
    Confirms via LLM that ALL stated requirements are satisfied.

Interface contract with MatlabRLOptimizer:
  result = await judgment_agent.judge(metrics, task_prompt)
  result.satisfied  -> bool: trigger RL early exit?
  result.suggestion -> str: hint for next iteration if not satisfied
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class JudgmentResult:
    satisfied: bool
    suggestion: str = ""
    reasons: List[str] = field(default_factory=list)
    metrics_snapshot: Dict[str, float] = field(default_factory=dict)
    next_action: str = "tune_params"  # "done" | "tune_params" | "modify_law"


def _extract_numeric_requirements(prompt: str) -> Dict[str, Any]:
    """Parse numeric performance requirements from task prompt (regex fallback)."""
    reqs: Dict[str, Any] = {}

    # hit_rate >= X%
    for pat in [
        r"命中率\s*[>=>=]+\s*(\d+(?:\.\d+)?)\s*%",
        r"hit[_\s]*rate\s*[>=>=]+\s*(\d+(?:\.\d+)?)",
    ]:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            reqs["hit_rate_min"] = float(m.group(1))
            break

    # SEP / miss <= X m
    for pat in [
        r"(?:脱靶量|SEP|miss)\s*[<=<=]+\s*(\d+(?:\.\d+)?)\s*m",
        r"miss\s*distance\s*[<=<=]+\s*(\d+(?:\.\d+)?)",
    ]:
        m = re.search(pat, prompt, re.IGNORECASE)
        if m:
            reqs["sep_max"] = float(m.group(1))
            break

    # PeakNy <= X g
    m = re.search(
        r"(?:峰值法向过载|法向过载|PeakNy|peak_ny)\s*[<=<=]+\s*(\d+(?:\.\d+)?)\s*g",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["peak_ny_max"] = float(m.group(1))

    # PM range: [X, Y] or >= X
    m = re.search(
        r"PM\s*(?:在|in|∈)\s*\[?\s*(\d+(?:\.\d+)?)\s*[,~到\-]\s*(\d+(?:\.\d+)?)",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["pm_min"] = float(m.group(1))
        reqs["pm_max"] = float(m.group(2))
    else:
        for pat in [
            r"PM\s*[>=>=]+\s*(\d+(?:\.\d+)?)\s*°?",
            r"相位裕度\s*[>=>=]+\s*(\d+(?:\.\d+)?)",
        ]:
            m = re.search(pat, prompt, re.IGNORECASE)
            if m:
                reqs["pm_min"] = float(m.group(1))
                break

    # BW in range [X, Y]
    m = re.search(
        r"BW\s*(?:在|in)\s*\[?\s*(\d+(?:\.\d+)?)\s*[,~到]\s*(\d+(?:\.\d+)?)",
        prompt, re.IGNORECASE,
    )
    if m:
        reqs["bw_min"] = float(m.group(1))
        reqs["bw_max"] = float(m.group(2))

    return reqs


def _rule_based_check(
    metrics: Dict[str, float],
    reqs: Dict[str, Any],
) -> tuple:
    """Fast numeric check. Returns (satisfied: bool, reasons: list[str])."""
    if not reqs:
        return False, ["未检测到数值要求，保守返回不满足"]

    satisfied = True
    reasons: List[str] = []

    if "hit_rate_min" in reqs:
        hr = metrics.get("hit_rate", 0.0)
        ok = hr >= reqs["hit_rate_min"]
        satisfied = satisfied and ok
        reasons.append(
            f"命中率 {hr:.1f}% {'>=' if ok else '<'} {reqs['hit_rate_min']:.1f}%"
            + (" [OK]" if ok else " [NG]")
        )

    if "sep_max" in reqs:
        sep = metrics.get("SEP", metrics.get("miss_distance", 999.0))
        ok = sep <= reqs["sep_max"]
        satisfied = satisfied and ok
        reasons.append(
            f"SEP {sep:.2f}m {'<=' if ok else '>'} {reqs['sep_max']:.2f}m"
            + (" [OK]" if ok else " [NG]")
        )

    if "peak_ny_max" in reqs:
        pny = metrics.get("peak_ny", metrics.get("peak_n", 0.0))
        if pny <= 0.0:
            reasons.append("PeakNy 数据不可用（跳过约束）")
        else:
            ok = pny <= reqs["peak_ny_max"]
            satisfied = satisfied and ok
            reasons.append(
                f"PeakNy {pny:.2f}g {'<=' if ok else '>'} {reqs['peak_ny_max']:.2f}g"
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
                f"PM {pm:.1f}deg {'>=' if ok else '<'} {reqs['pm_min']:.1f}deg"
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


class JudgmentAgent:
    """
    Layer 3 per-episode judgment agent.

    Usage in RL optimizer:
        judgment = JudgmentAgent(reflection_agent=..., task_prompt=...)
        result = await judgment.judge(metrics)
        if result.satisfied:
            break  # early exit from RL loop
    """

    def __init__(
        self,
        reflection_agent: Optional[Any] = None,
        task_prompt: str = "",
    ):
        self._reflection_agent = reflection_agent
        self._task_prompt = task_prompt
        self._reqs: Dict[str, Any] = {}
        self._reqs_from_llm: bool = False
        if task_prompt:
            self._reqs = _extract_numeric_requirements(task_prompt)
            logger.info(f"[JudgmentAgent] Regex requirements: {self._reqs}")

    def update_task_prompt(self, prompt: str) -> None:
        self._task_prompt = prompt
        self._reqs = _extract_numeric_requirements(prompt)
        self._reqs_from_llm = False

    async def _extract_requirements_llm(self) -> Dict[str, Any]:
        """Use the reflection agent's LLM to extract numeric requirements.

        Returns a dict with the same keys as _extract_numeric_requirements().
        Falls back to empty dict on any failure.
        """
        llm = getattr(self._reflection_agent, "llm", None)
        if llm is None or not self._task_prompt:
            return {}

        extract_prompt = (
            "从以下任务描述中提取数值性能要求，以JSON格式返回。\n"
            f"任务描述：{self._task_prompt}\n\n"
            "返回格式（只包含任务中明确提及的指标，未提及的不要出现）：\n"
            "{\n"
            '  "hit_rate_min": 92.0,   // 命中率下限 (%)\n'
            '  "sep_max": 5.0,         // SEP/脱靶量上限 (m)\n'
            '  "peak_ny_max": 20.0,    // 峰值法向过载上限 (g)\n'
            '  "pm_min": 45.0,         // 相位裕度下限 (deg)\n'
            '  "pm_max": 65.0,         // 相位裕度上限 (deg，若有区间要求则填写)\n'
            '  "bw_min": 12.0,         // 带宽下限 (rad/s)\n'
            '  "bw_max": 22.0          // 带宽上限 (rad/s)\n'
            "}\n"
            "只返回JSON，不要任何说明文字。"
        )

        try:
            from langchain_core.messages import HumanMessage
            response = await llm.ainvoke([HumanMessage(content=extract_prompt)])
            content = response.content
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            content = re.sub(r"```(?:json)?", "", content).strip().strip("`").strip()
            parsed = json.loads(content)
            result = {
                k: float(v)
                for k, v in parsed.items()
                if isinstance(v, (int, float)) and v is not None
            }
            logger.info(f"[JudgmentAgent] LLM-extracted requirements: {result}")
            return result
        except Exception as exc:
            logger.warning(f"[JudgmentAgent] LLM requirement extraction failed: {exc}")
            return {}

    async def judge(
        self,
        metrics: Dict[str, float],
        task_prompt: Optional[str] = None,
    ) -> JudgmentResult:
        """Evaluate metrics against task requirements.

        Level 0: LLM requirement extraction (once, on first call).
        Level 1: numeric rule check (always runs, fast).
        Level 2: LLM reflection (only when Level 1 passes).
        """
        if task_prompt:
            self._task_prompt = task_prompt
            self._reqs = _extract_numeric_requirements(task_prompt)
            self._reqs_from_llm = False

        # Level 0: LLM extraction (one-time, overrides regex result)
        if not self._reqs_from_llm and self._task_prompt:
            llm_reqs = await self._extract_requirements_llm()
            if llm_reqs:
                self._reqs = llm_reqs
            self._reqs_from_llm = True

        # Level 1: Rule check
        rule_ok, reasons = _rule_based_check(metrics, self._reqs)

        if not rule_ok:
            # Rules say not satisfied - skip LLM to save cost
            suggestion = "; ".join(r for r in reasons if "[NG]" in r)
            return JudgmentResult(
                satisfied=False,
                suggestion=suggestion,
                reasons=reasons,
                metrics_snapshot=dict(metrics),
                next_action="tune_params",
            )

        # Level 2: LLM reflection (rules passed)
        if self._reflection_agent is not None and self._task_prompt:
            try:
                ref = await self._reflection_agent.reflect(
                    self._task_prompt,
                    {"metrics": metrics},
                )
                llm_ok = not ref.get("needs_optimization", True)
                suggestion = ref.get("suggestion", "")

                next_action = "done"
                if not llm_ok:
                    low = suggestion.lower()
                    if any(kw in low for kw in ("修改制导律", "modify_law", "重新设计", "结构")):
                        next_action = "modify_law"
                    else:
                        next_action = "tune_params"

                return JudgmentResult(
                    satisfied=llm_ok,
                    suggestion=suggestion,
                    reasons=reasons + [f"LLM判断: {'满足' if llm_ok else '不满足'}"],
                    metrics_snapshot=dict(metrics),
                    next_action=next_action,
                )
            except (Exception, asyncio.CancelledError) as exc:
                logger.warning(f"[JudgmentAgent] LLM reflection failed: {exc}; using rule result")

        # Only rules available - report satisfied
        return JudgmentResult(
            satisfied=True,
            suggestion="规则检查通过（无 LLM 反思）",
            reasons=reasons,
            metrics_snapshot=dict(metrics),
            next_action="done",
        )

    async def reflect(
        self,
        task_prompt: str,
        input_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Adapter so JudgmentAgent can be used as a drop-in replacement for
        ReflectionAgent inside MatlabRLOptimizer.

        RL optimizer calls active_reflector.reflect(task_prompt, data) per
        episode. This adapter forwards to judge() and converts the result
        to the dict format expected by the optimizer.
        """
        metrics = input_data.get("metrics", input_data)
        if not isinstance(metrics, dict):
            metrics = {}
        result = await self.judge(metrics, task_prompt=task_prompt)
        return {
            "needs_optimization": not result.satisfied,
            "suggestion":         result.suggestion,
            "next_action":        result.next_action,
            "reasons":            result.reasons,
            "satisfied":          result.satisfied,
        }
