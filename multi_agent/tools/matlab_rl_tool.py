#!/usr/bin/env python3
"""
MATLAB RL Optimization Tools for Hermes Agent

Provides two tools:
  - MatlabRLOptimizationTool : run RL-based autopilot parameter optimisation
  - ExtractMatlabParamsTool  : dynamically extract all numeric params from a MATLAB script
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MatlabRLOptimizationTool:
    """
    Hermes tool: RL-based optimisation of guidance law + autopilot parameters.

    Automatically extracts all tunable dp.* parameters from the generated MATLAB
    simulation script, builds an 11-dim state/action space, runs PPO optimisation
    episodes, evaluates each candidate via Monte Carlo simulation, and writes the
    best parameters back to ParameterExperience (long-term memory).
    """

    name = "matlab_rl_optimize"
    description = """
    Run RL-based optimisation of guidance system parameters (guidance law + autopilot).
    Dynamically extracts all tunable dp.* parameters from the generated MATLAB script:
      - Guidance law: N_guidance, R_switch, gama_max_deg
      - Autopilot (3-loop): w1, zeta1, tao1, w2, zeta2, tao2, w3, zeta3
    Builds an 11-dim continuous action space, runs PPO policy-gradient optimisation,
    and persists the best parameters to ParameterExperience.

    On every new best, the reflection agent (auto-injected by HermesIntegration)
    is consulted with the user's full task prompt. When it confirms that ALL
    stated requirements are satisfied, the loop exits with status
    'task_requirements_met', best params are written back, and the caller
    should proceed to save the model and generate the report.

    Use this when you need to:
    - Improve hit rate, phase margin (>30°), gain margin (>6 dB), or reduce miss distance
    - Tune proportional navigation coefficient or guidance switching range
    - Auto-tune three-loop autopilot bandwidth and damping settings
    - Persist optimal parameters to ParameterExperience after optimisation
    """

    input_schema = {
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": "Absolute path to the generated MATLAB simulation script (.m)",
            },
            "mission_conditions": {
                "type": "string",
                "description": (
                    "Mission condition string.  Examples:\n"
                    "  'run_A = true; sub_A = [];'  → category A, all subcases\n"
                    "  'run_B = true; sub_B = [1,3];' → category B subcases 1 and 3\n"
                    "  'run_C = false;'              → skip category C\n"
                    "Multiple categories can be combined in one string."
                ),
            },
            "max_episodes": {
                "type": "integer",
                "description": "Maximum RL optimisation episodes (default: 30)",
                "default": 30,
            },
            "nmc_per_eval": {
                "type": "integer",
                "description": "Monte Carlo runs per episode evaluation (default: 10)",
                "default": 10,
            },
            "task_context": {
                "type": "object",
                "description": "Extra context dict stored alongside the experience entry",
            },
            "miss_threshold": {
                "type": "number",
                "description": (
                    "Optional numeric miss-distance hint (metres). Forwarded to "
                    "the reflection agent as additional context only — it is NOT "
                    "used as a hard early-exit criterion. The reflection agent "
                    "alone decides when the user's full task requirements are met."
                ),
            },
            "task_prompt": {
                "type": "string",
                "description": (
                    "Original user task description (Chinese or English). "
                    "USUALLY auto-injected by the integration layer — only "
                    "override here if you have a different prompt for this RL run. "
                    "On every new best, the reflection agent uses this to decide "
                    "whether the full task requirement is already met. RL exits "
                    "with status='task_requirements_met' on a positive verdict."
                ),
            },
            "reflect_every": {
                "type": "integer",
                "description": (
                    "Cadence (in episodes) for invoking the reflection agent. "
                    "1 = check on every new best (default), N = every N-th new best. "
                    "Higher values reduce LLM cost."
                ),
                "default": 1,
            },
        },
        "required": [],
    }

    def __init__(self, *args, **kwargs):
        self.simulator = None
        self.parameter_experience = None
        self.reflection_agent = None
        self._default_task_prompt: Optional[str] = None
        self._default_mission_conditions: Optional[str] = None
        self._optimizer = None
        super().__init__(*args, **kwargs)

    def set_simulator(self, simulator) -> None:
        self.simulator = simulator

    def set_parameter_experience(self, parameter_experience) -> None:
        self.parameter_experience = parameter_experience

    def set_reflection_agent(self, reflection_agent) -> None:
        """Inject the reflection agent so RL can evaluate user-task fulfilment per episode."""
        self.reflection_agent = reflection_agent

    def set_mission_conditions(self, conditions_str: str) -> None:
        """Inject user-resolved mission conditions as fallback for Hermes tool calls."""
        self._default_mission_conditions = conditions_str or None

    def set_task_prompt(self, prompt: Optional[str]) -> None:
        """Cache the user's original task prompt so Hermes-orchestrated calls
        automatically receive it without the LLM having to forward it explicitly."""
        self._default_task_prompt = prompt

    def _get_optimizer(self):
        from ..rl.matlab_rl_optimizer import MatlabRLOptimizer
        if self._optimizer is None:
            self._optimizer = MatlabRLOptimizer(
                simulator=self.simulator,
                parameter_experience=self.parameter_experience,
                reflection_agent=self.reflection_agent,
            )
        else:
            self._optimizer.simulator = self.simulator
            self._optimizer.parameter_experience = self.parameter_experience
            self._optimizer.reflection_agent = self.reflection_agent
        return self._optimizer

    async def execute(
        self,
        script_path: Optional[str] = None,
        mission_conditions: Optional[str] = None,
        max_episodes: int = 30,
        nmc_per_eval: int = 10,
        task_context: Optional[Dict[str, Any]] = None,
        miss_threshold: Optional[float] = None,
        task_prompt: Optional[str] = None,
        reflect_every: int = 1,
    ) -> Dict[str, Any]:
        """Execute RL optimisation and return best parameters + metrics."""
        try:
            from ..rl.matlab_rl_optimizer import parse_mission_conditions

            optimizer = self._get_optimizer()
            optimizer.max_episodes  = max_episodes
            optimizer.nmc_per_eval  = nmc_per_eval

            # Use caller-supplied conditions; fall back to injected default
            _eff_cond_str = mission_conditions or self._default_mission_conditions
            parsed_conditions: Optional[Dict[str, List[int]]] = None
            if _eff_cond_str:
                parsed_conditions = parse_mission_conditions(_eff_cond_str)
                logger.info(f"Parsed mission conditions: {parsed_conditions}")

            if not script_path or not os.path.exists(str(script_path)):
                script_path = self._find_latest_matlab_script()
                if script_path:
                    logger.info(f"Auto-discovered MATLAB script: {script_path}")

            # Resolve the effective task prompt:
            #   1. Explicit ``task_prompt`` argument wins (Hermes can override)
            #   2. ``task_context['prompt' | 'task_prompt']`` next
            #   3. Cached default injected by HermesIntegration (auto-path)
            effective_prompt = (
                task_prompt
                or (task_context or {}).get("prompt")
                or (task_context or {}).get("task_prompt")
                or self._default_task_prompt
            )
            if effective_prompt is None and self.reflection_agent is not None:
                logger.warning(
                    "matlab_rl_optimize: no task_prompt available — "
                    "per-episode reflection will be skipped. Pass task_prompt "
                    "or use HermesIntegration.initialize_with_tools(user_prompt=…)."
                )

            result = await optimizer.optimize(
                script_path=script_path,
                mission_conditions=parsed_conditions,
                max_episodes=max_episodes,
                nmc=nmc_per_eval,
                task_context=task_context or {},
                miss_threshold=miss_threshold,
                task_prompt=effective_prompt,
                reflection_agent=self.reflection_agent,
                reflect_every=reflect_every,
            )

            improvement   = result["best_reward"] - result["baseline_reward"]
            opt_status    = result.get("status", "success")
            best_miss     = result["best_metrics"].get("miss_distance", 99.0)
            reflection    = result.get("reflection")

            # Classify reflection suggestion → next_action_hint so Hermes doesn't
            # need to parse free-text to decide the next design-path step.
            _suggestion_text = (reflection or {}).get("suggestion", "").lower()
            _needs_opt = bool((reflection or {}).get("needs_optimization", True))
            _MODIFY_SIGNALS = [
                "制导律", "算法结构", "modify_law", "修改制导律", "新的制导",
                "重新设计", "滑模", "预测制导", "guidance law", "algorithm",
            ]
            if not _needs_opt or opt_status == "task_requirements_met":
                _next_hint = "done"
            elif opt_status == "needs_design_path_change" or any(sig in _suggestion_text for sig in _MODIFY_SIGNALS):
                _next_hint = "modify_law"
            else:
                _next_hint = "tune_params"

            if opt_status == "task_requirements_met":
                suggestion = (reflection or {}).get("suggestion", "")
                status_msg = (
                    f"RL early-stopped at episode {result['total_episodes']}: "
                    f"reflection agent confirmed the user's task requirements are "
                    f"satisfied (miss={best_miss:.4f} m). "
                    f"Best params written to ParameterExperience. Caller should "
                    f"now save the model and generate the simulation report. "
                    f"Suggestion: {suggestion[:200]}"
                )
                # ── Auto-persist snapshot so cli_agent Step 5 can build the report ──
                # even when the direct-RL Step 3 was skipped (optimization_workflow
                # disabled) and rl_result is None.
                try:
                    import json as _json
                    import pathlib as _pl
                    import time as _time
                    import re as _re
                    _out = _pl.Path("./guidance_output")
                    _out.mkdir(parents=True, exist_ok=True)
                    _snapshot = {
                        "status":          opt_status,
                        "best_params":     result["best_params"],
                        "best_metrics":    result["best_metrics"],
                        "best_reward":     result["best_reward"],
                        "baseline_reward": result["baseline_reward"],
                        "total_episodes":  result["total_episodes"],
                        "source":          "hermes_rl_tool",
                        "timestamp":       _time.time(),
                    }
                    _snap_path = _out / "hermes_rl_best.json"
                    _snap_path.write_text(
                        _json.dumps(_snapshot, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    logger.info(f"[RL tool] task_requirements_met snapshot → {_snap_path}")
                    status_msg += f"\nBest-params snapshot saved: {_snap_path}"
                    # Patch and save the MATLAB script with best params so the model
                    # file is available for the report and for future reuse.
                    _sp = str(script_path) if script_path else ""
                    if _sp and os.path.exists(_sp):
                        with open(_sp, "r", encoding="utf-8", errors="ignore") as _f:
                            _script = _f.read()
                        for _k, _v in result["best_params"].items():
                            _script = _re.sub(
                                rf"(dp\.{_k}\s*=\s*)[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?\s*;",
                                f"dp.{_k} = {_v:.6f};",
                                _script,
                            )
                        _m_path = _out / "rl_best_params.m"
                        _m_path.write_text(_script, encoding="utf-8")
                        logger.info(f"[RL tool] Best-params MATLAB script → {_m_path}")
                        status_msg += f"\nBest-params MATLAB script: {_m_path}"
                except Exception as _snap_exc:
                    logger.warning(f"[RL tool] Snapshot/model save failed: {_snap_exc}")
            else:
                status_msg = (
                    f"RL optimisation completed ({result['total_episodes']} episodes). "
                    f"Best reward: {result['best_reward']:.3f} "
                    f"(baseline: {result['baseline_reward']:.3f}, "
                    f"improvement: {improvement:+.3f}). "
                    f"Best params written to ParameterExperience."
                )

            return {
                "status":                opt_status,
                "best_params":           result["best_params"],
                "best_metrics":          result["best_metrics"],
                "best_reward":           result["best_reward"],
                "baseline_reward":       result["baseline_reward"],
                "improvement":           float(improvement),
                "total_episodes":        result["total_episodes"],
                "miss_distance":         float(best_miss),
                "task_requirements_met": (opt_status == "task_requirements_met"),
                "reflection":            reflection,
                "next_action_hint":      _next_hint,
                "message":               status_msg,
            }
        except Exception as exc:
            logger.error(f"RL optimisation failed: {exc}", exc_info=True)
            return {"status": "error", "message": str(exc)}

    @staticmethod
    def _find_latest_matlab_script() -> Optional[str]:
        search_dirs = ["./matlab_scripts", "./guidance_output", "./output", "."]
        latest_path: Optional[str] = None
        latest_mtime = 0.0
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                # Skip every RL temp filename pattern (legacy + new + function-file)
                if (
                    fname.endswith(".m")
                    and not fname.startswith("_rl_tmp")
                    and not fname.startswith("rltmp_")
                    and "_rltmp_" not in fname
                ):
                    fp = os.path.join(d, fname)
                    mt = os.path.getmtime(fp)
                    if mt > latest_mtime:
                        latest_mtime = mt
                        latest_path = fp
        return latest_path


class ExtractMatlabParamsTool:
    """
    Hermes tool: dynamically extract all numeric parameters from a MATLAB script.

    Returns a typed dict of {param_name: float_value} for all numeric
    assignments found in the script.  Useful for inspecting available
    parameters before running optimisation.
    """

    name = "extract_matlab_params"
    description = """
    Dynamically extract all numeric parameter assignments from a generated
    MATLAB simulation script.  Returns parameter names and float values.
    Use this to inspect available parameters before running RL optimisation.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "script_path": {
                "type": "string",
                "description": "Absolute path to the MATLAB script (.m file)",
            },
            "param_group": {
                "type": "string",
                "enum": ["all", "tunable", "guidance", "autopilot", "physical"],
                "description": (
                    "Which parameter group to return (default: all). "
                    "'tunable' returns all 11 RL-tunable params (guidance + autopilot). "
                    "'guidance' returns N_guidance/R_switch/gama_max_deg only. "
                    "'autopilot' returns w1/zeta1/tao1/w2/zeta2/tao2/w3/zeta3 only. "
                    "'physical' returns mass/thrust/aero scale params."
                ),
                "default": "all",
            },
        },
        "required": ["script_path"],
    }

    async def execute(
        self,
        script_path: str,
        param_group: str = "all",
    ) -> Dict[str, Any]:
        """Extract parameters from MATLAB script and return as float dict."""
        try:
            from ..rl.matlab_rl_optimizer import (
                extract_matlab_params,
                extract_autopilot_params,
                extract_physical_params,
                ALL_TUNABLE_PARAM_SPECS,
                GUIDANCE_PARAM_SPECS,
                AUTOPILOT_PARAM_SPECS,
            )

            if not os.path.exists(script_path):
                return {"status": "error", "message": f"Script not found: {script_path}"}

            with open(script_path, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()

            if param_group in ("autopilot", "tunable", "guidance"):
                all_tunable = extract_autopilot_params(content)  # now returns all 11 params
                if param_group == "guidance":
                    params = {k: v for k, v in all_tunable.items() if k in GUIDANCE_PARAM_SPECS}
                elif param_group == "autopilot":
                    params = {k: v for k, v in all_tunable.items() if k in AUTOPILOT_PARAM_SPECS}
                else:  # tunable
                    params = all_tunable
            elif param_group == "physical":
                params = extract_physical_params(content)
            else:
                params = extract_matlab_params(content)

            params = {k: float(v) for k, v in params.items()}

            return {
                "status":        "success",
                "script_path":   script_path,
                "param_group":   param_group,
                "params":        params,
                "count":         len(params),
                "tunable_specs": {
                    k: {kk: float(vv) for kk, vv in spec.items()}
                    for k, spec in ALL_TUNABLE_PARAM_SPECS.items()
                },
            }
        except Exception as exc:
            logger.error(f"Parameter extraction failed: {exc}")
            return {"status": "error", "message": str(exc)}
