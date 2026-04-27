#!/usr/bin/env python3
"""
OptimizationWorkflow — Layer 3 async workflow.

Entry point for the RL-based optimization pipeline.
Called by cli_agent.py when Hermes (Layer 2) has generated a script
and initial simulation results do NOT satisfy requirements.

Flow:
  1. RL Optimizer runs PPO optimization on the script.
     - After each episode that produces a new best → JudgmentAgent.judge()
     - Early exit if JudgmentAgent.satisfied == True
  2. ReflectionAgent provides final deep analysis.
  3a. If satisfied:
       - Write back params + model to ParameterExperience
       - Return status="done" + report data
  3b. If not satisfied:
       - Return status="needs_iteration" + suggestion + next_action
         (caller feeds suggestion back to Hermes as prev_suggestion)
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OptimizationWorkflow:
    """
    Async Layer 3 workflow that integrates:
      - MatlabRLOptimizer (RL optimization)
      - JudgmentAgent     (per-episode evaluation)
      - ReflectionAgent   (final analysis)
      - ParameterExperience (experience writeback)
    """

    def __init__(
        self,
        rl_optimizer=None,
        judgment_agent=None,
        reflection_agent=None,
        parameter_experience=None,
        output_dir: str = "./guidance_output",
    ):
        self.rl_optimizer = rl_optimizer
        self.judgment_agent = judgment_agent
        self.reflection_agent = reflection_agent
        self.parameter_experience = parameter_experience
        self.output_dir = output_dir

    async def run(
        self,
        script_path: str,
        task_prompt: str,
        mission_conditions: Optional[Dict[str, List[int]]] = None,
        initial_metrics: Optional[Dict[str, float]] = None,
        directly_satisfied: bool = False,
        max_episodes: Optional[int] = None,
        nmc: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run the Layer 3 optimization workflow.

        Parameters
        ----------
        script_path : str
            Path to the generated .m script (monte_carlo_single style).
        task_prompt : str
            User's full task description (used by judgment + reflection).
        mission_conditions : dict, optional
            Parsed T/G/AP/R conditions dict.
        initial_metrics : dict, optional
            Metrics from Hermes Layer 2 run_simulation call.
        directly_satisfied : bool
            If True (judge_requirements already returned satisfied),
            skip RL and go directly to Reflection.
        max_episodes, nmc : optional overrides.

        Returns
        -------
        dict with keys:
            status         : "done" | "needs_iteration"
            best_params    : dict (tunable params)
            best_metrics   : dict (simulation metrics)
            suggestion     : str (only when needs_iteration)
            next_action    : "tune_params" | "modify_law" (only when needs_iteration)
            report_path    : str (only when done)
        """
        _t0 = datetime.now()
        logger.info(
            f"[OptimWorkflow] Starting | directly_satisfied={directly_satisfied} | "
            f"script={os.path.basename(script_path)}"
        )

        rl_result: Dict[str, Any] = {}
        best_params: Dict[str, float] = {}
        best_metrics: Dict[str, float] = initial_metrics or {}

        # ── Path A: directly satisfied from Layer 2 judge_requirements ───────
        if directly_satisfied and initial_metrics:
            logger.info("[OptimWorkflow] Skipping RL (directly satisfied by Layer 2)")
            best_metrics = initial_metrics
        else:
            # ── Path B: RL optimization loop ──────────────────────────────────
            if self.rl_optimizer is None:
                logger.warning("[OptimWorkflow] No RL optimizer; using initial_metrics")
            else:
                # Inject judgment agent into RL optimizer for per-episode
                # lightweight evaluation (rule-check + optional LLM).
                # ReflectionAgent is NOT used inside the RL loop — it runs
                # once after RL finishes for deep analysis.
                if self.judgment_agent is not None:
                    self.judgment_agent.update_task_prompt(task_prompt)
                    self.rl_optimizer.reflection_agent = self.judgment_agent

                try:
                    rl_result = await self.rl_optimizer.optimize(
                        script_path=script_path,
                        mission_conditions=mission_conditions,
                        max_episodes=max_episodes,
                        nmc=nmc,
                        task_prompt=task_prompt,
                        reflection_agent=self.judgment_agent,  # lightweight per-episode judge
                    )
                    best_params  = rl_result.get("best_params", {})
                    best_metrics = rl_result.get("best_metrics", best_metrics)
                    logger.info(
                        f"[OptimWorkflow] RL done: status={rl_result.get('status')} "
                        f"episodes={rl_result.get('total_episodes', 0)} "
                        f"best_reward={rl_result.get('best_reward', 0):.3f}"
                    )
                except Exception as exc:
                    logger.error(f"[OptimWorkflow] RL optimizer failed: {exc}")
                    best_metrics = initial_metrics or {}

        # ── Reflection Agent — always runs ────────────────────────────────────
        reflection_result: Dict[str, Any] = {}
        if self.reflection_agent is not None and task_prompt:
            try:
                reflection_result = await self.reflection_agent.reflect(
                    task_prompt,
                    {"parameters": best_params, "metrics": best_metrics},
                )
                logger.info(
                    f"[OptimWorkflow] Reflection: "
                    f"needs_optimization={reflection_result.get('needs_optimization')} | "
                    f"{str(reflection_result.get('suggestion', ''))[:150]}"
                )
            except Exception as exc:
                logger.error(f"[OptimWorkflow] Reflection agent failed: {exc}")
                reflection_result = {"needs_optimization": False, "suggestion": str(exc)}

        needs_opt = reflection_result.get("needs_optimization", False)
        suggestion = reflection_result.get("suggestion", "")

        # Determine next_action from suggestion text
        next_action = "tune_params"
        if suggestion:
            low = suggestion.lower()
            if any(kw in low for kw in ("修改制导律", "modify_law", "重新设计", "结构")):
                next_action = "modify_law"

        # ── Path A: satisfied → write back + report ───────────────────────────
        if not needs_opt:
            writeback_ok = await self._writeback_experience(
                script_path, best_params, best_metrics, task_prompt
            )
            report_path = await self._generate_report(
                script_path, best_params, best_metrics, task_prompt,
                rl_result=rl_result,
                reflection_result=reflection_result,
                elapsed=(datetime.now() - _t0).total_seconds(),
            )
            logger.info(
                f"[OptimWorkflow] DONE ✓ | "
                f"hit={best_metrics.get('hit_rate', 0):.1f}% "
                f"SEP={best_metrics.get('SEP', 99):.2f}m "
                f"PM={best_metrics.get('pitch_PM', 0):.1f}°"
            )
            return {
                "status":       "done",
                "best_params":  best_params,
                "best_metrics": best_metrics,
                "suggestion":   suggestion,
                "next_action":  "done",
                "report_path":  report_path,
                "writeback_ok": writeback_ok,
                "elapsed_sec":  (datetime.now() - _t0).total_seconds(),
            }

        # ── Path B: not satisfied → return suggestion to Layer 1 ─────────────
        logger.info(
            f"[OptimWorkflow] NEEDS_ITERATION | next_action={next_action} | "
            f"{suggestion[:120]}"
        )
        return {
            "status":       "needs_iteration",
            "best_params":  best_params,
            "best_metrics": best_metrics,
            "suggestion":   suggestion,
            "next_action":  next_action,
            "report_path":  "",
            "elapsed_sec":  (datetime.now() - _t0).total_seconds(),
        }

    async def _writeback_experience(
        self,
        script_path: str,
        params: Dict[str, float],
        metrics: Dict[str, float],
        task_prompt: str,
    ) -> bool:
        """Write best params and model to ParameterExperience."""
        if self.parameter_experience is None:
            return False
        try:
            pe_params = {f"dp_{k}": v for k, v in params.items()}
            fitness = (
                metrics.get("hit_rate", 0.0) / 100.0
                - metrics.get("SEP", 50.0) / 50.0 * 0.3
            )
            await self.parameter_experience.store_experience(
                parameters=pe_params,
                objectives=metrics,
                fitness=fitness,
                task_context={"prompt": task_prompt[:200]},
            )

            # Copy script to experience_base/models/
            if script_path and os.path.isfile(script_path):
                model_dir = Path(self.output_dir) / "parameter_experience_base" / "models"
                model_dir.mkdir(parents=True, exist_ok=True)
                import shutil, time as _time
                dest = model_dir / f"success_{int(_time.time())}_{os.path.basename(script_path)}"
                shutil.copy2(script_path, str(dest))
                logger.info(f"[OptimWorkflow] Model saved → {dest}")
            return True
        except Exception as exc:
            logger.error(f"[OptimWorkflow] Experience writeback failed: {exc}")
            return False

    async def _generate_report(
        self,
        script_path: str,
        params: Dict[str, float],
        metrics: Dict[str, float],
        task_prompt: str,
        rl_result: Dict[str, Any] = None,
        reflection_result: Dict[str, Any] = None,
        elapsed: float = 0.0,
    ) -> str:
        """Write a JSON+TXT report to output_dir and return the path."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_dir = Path(self.output_dir) / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = str(report_dir / f"report_{ts}.json")

            report = {
                "timestamp": ts,
                "task_prompt": task_prompt[:500],
                "script_path": script_path,
                "elapsed_sec": elapsed,
                "best_params": params,
                "best_metrics": metrics,
                "rl_summary": {
                    "status":        (rl_result or {}).get("status", ""),
                    "total_episodes":(rl_result or {}).get("total_episodes", 0),
                    "best_reward":   (rl_result or {}).get("best_reward", 0.0),
                },
                "reflection": {
                    "needs_optimization": (reflection_result or {}).get("needs_optimization"),
                    "suggestion": (reflection_result or {}).get("suggestion", "")[:1000],
                },
                "metrics_display": {
                    "命中率%":  f"{metrics.get('hit_rate', 0):.1f}",
                    "SEP(m)":   f"{metrics.get('SEP', metrics.get('miss_distance', 0)):.2f}",
                    "PeakNy(g)":f"{metrics.get('peak_ny', metrics.get('peak_n', 0)):.2f}",
                    "PM(°)":    f"{metrics.get('pitch_PM', 0):.1f}",
                    "BW(r/s)":  f"{metrics.get('pitch_BW', 0):.1f}",
                },
            }

            with open(report_path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, ensure_ascii=False, indent=2)
            logger.info(f"[OptimWorkflow] Report saved → {report_path}")
            return report_path
        except Exception as exc:
            logger.error(f"[OptimWorkflow] Report generation failed: {exc}")
            return ""
