"""Constraint-aware local search — refines PPO best in parameter neighbourhood."""

from __future__ import annotations

import copy
import logging
import math
import random
from typing import Any, Dict, List, Optional

import numpy as np

from multi_agent.integration.design_path_policy import metrics_summary_line
from multi_agent.logging.log_verbosity import is_verbose, should_log_cls_step
from multi_agent.rl.episode_log import EpisodeJsonlLogger
from multi_agent.rl.matlab_rl_optimizer import (
    ALL_TUNABLE_PARAM_SPECS,
    MatlabRLOptimizer,
)
from multi_agent.rl.metric_utils import get_peak_ny, get_peak_ny_max
from multi_agent.rl.metric_constraints import (
    constraints_satisfied,
    is_better_borderline_peak,
    is_better_constrained,
    is_borderline_hit_sep_ok,
    regressed_satisfied_metrics,
    resolve_requirements,
    satisfied_metric_keys,
)

logger = logging.getLogger(__name__)


def _cls_skip_borderline_for_full_task(task_prompt: str, reqs: Dict[str, Any]) -> bool:
    """Skip hit/SEP-only borderline pick when prompt requires all five metrics."""
    if not task_prompt:
        return False
    try:
        from multi_agent.integration.design_path_policy import is_optimization_task
        from multi_agent.integration.judgment_agent import requirements_complete

        return is_optimization_task(task_prompt) and requirements_complete(reqs, task_prompt)
    except Exception:
        return False


class ConstraintLocalSearch:
    """Gaussian-ish random walk around a centre parameter vector."""

    def __init__(
        self,
        rl_backend: MatlabRLOptimizer,
        max_iterations: int = 50,
        step_scale: float = 0.08,
        seed: Optional[int] = None,
    ):
        self.rl_backend = rl_backend
        self.max_iterations = max(1, int(max_iterations))
        self.step_scale = float(step_scale)
        self._rng = random.Random(seed)

    def _perturb(self, centre: Dict[str, float]) -> Dict[str, float]:
        return self._perturb_with_scale(centre, self.step_scale)

    def _perturb_with_scale(self, centre: Dict[str, float], scale: float) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for k, spec in ALL_TUNABLE_PARAM_SPECS.items():
            lo, hi = spec["min"], spec["max"]
            span = hi - lo
            delta = self._rng.uniform(-scale, scale) * span
            out[k] = float(np.clip(centre.get(k, spec["nominal"]) + delta, lo, hi))
        return out

    async def refine(
        self,
        center_params: Dict[str, float],
        *,
        script_path: Optional[str],
        mission_conditions: Optional[Dict[str, List[int]]],
        nmc: int,
        task_prompt: Optional[str] = None,
        metric_requirements: Optional[Dict[str, Any]] = None,
        judgment_agent: Any = None,
        episode_logger: Optional[EpisodeJsonlLogger] = None,
        reference_params: Optional[Dict[str, float]] = None,
        reference_metrics: Optional[Dict[str, float]] = None,
        borderline_select: bool = True,
        borderline_hit_min_pct: float = 92.0,
        borderline_sep_max_m: float = 7.0,
        prefer_reference_peak: bool = True,
        protect_satisfied: bool = True,
    ) -> Dict[str, Any]:
        reqs = resolve_requirements(metric_requirements, task_prompt, judgment_agent)
        centre = copy.deepcopy(center_params)
        if script_path and self.rl_backend:
            self.rl_backend.extract_params_from_script(script_path)

        best_params = copy.deepcopy(centre)
        best_metrics: Dict[str, float] = {}
        best_fitness = -1.0
        best_constrained_params: Optional[Dict[str, float]] = None
        best_constrained_metrics: Optional[Dict[str, float]] = None
        best_constrained_fitness = -1.0
        best_borderline_params: Optional[Dict[str, float]] = None
        best_borderline_metrics: Optional[Dict[str, float]] = None

        if (
            prefer_reference_peak
            and reference_metrics
            and is_borderline_hit_sep_ok(
                reference_metrics,
                hit_min_pct=borderline_hit_min_pct,
                sep_max_m=borderline_sep_max_m,
            )
        ):
            best_borderline_params = copy.deepcopy(reference_params or centre)
            best_borderline_metrics = copy.deepcopy(reference_metrics)
            if reference_params:
                best_params = copy.deepcopy(reference_params)
                best_metrics = copy.deepcopy(reference_metrics)
                best_fitness = self.rl_backend._compute_pe_fitness(reference_metrics)
        center_metrics = await self.rl_backend._run_simulation_with_params(
            centre, mission_conditions, script_path, nmc
        )
        center_reward = self.rl_backend._compute_reward(center_metrics)
        center_fitness = self.rl_backend._compute_pe_fitness(center_metrics)
        if not best_metrics:
            best_metrics = copy.deepcopy(center_metrics)
            best_fitness = center_fitness
        elif get_peak_ny(center_metrics) < get_peak_ny(best_metrics):
            best_params = copy.deepcopy(centre)
            best_metrics = copy.deepcopy(center_metrics)
            best_fitness = center_fitness
        center_satisfied = constraints_satisfied(center_metrics, reqs)
        if center_satisfied:
            best_constrained_params = copy.deepcopy(centre)
            best_constrained_metrics = copy.deepcopy(center_metrics)
            best_constrained_fitness = center_fitness
        if borderline_select and is_borderline_hit_sep_ok(
            center_metrics,
            hit_min_pct=borderline_hit_min_pct,
            sep_max_m=borderline_sep_max_m,
        ):
            if is_better_borderline_peak(center_metrics, best_borderline_metrics):
                best_borderline_params = copy.deepcopy(centre)
                best_borderline_metrics = copy.deepcopy(center_metrics)

        if episode_logger:
            episode_logger.write_episode(
                optimizer="ConstraintLocalSearch",
                episode=0,
                params=centre,
                metrics=center_metrics,
                reward=center_reward,
                fitness=center_fitness,
                constrained=constraints_satisfied(center_metrics, reqs),
                extra={"phase": "center"},
            )

        # Metrics already meeting their requirement at the working best must not
        # regress: candidates that break any of these are rejected. The set grows
        # monotonically as the best improves. Empty when no requirement is parsed,
        # which reduces to the original (unprotected) behaviour.
        protected_satisfied = (
            satisfied_metric_keys(best_metrics, reqs) if protect_satisfied else set()
        )
        if protected_satisfied:
            logger.info(
                "[CLS] protect_satisfied on — already-met metrics held: "
                f"{sorted(protected_satisfied)}"
            )

        history: List[Dict[str, Any]] = []
        iterations_run = 0

        if center_satisfied:
            logger.info(
                "[CLS] All constraints satisfied at center — stopping early "
                f"(PeakN_max={get_peak_ny_max(center_metrics):.2f}g)"
            )
        else:
            for it in range(1, self.max_iterations + 1):
                iterations_run = it
                _ref_peak = get_peak_ny(
                    best_borderline_metrics or best_metrics or reference_metrics or {}
                )
                _peak_limit = float(getattr(self.rl_backend, "_peak_n_max", 20.0))
                if 0.0 < _ref_peak <= _peak_limit:
                    candidate = self._perturb_with_scale(
                        centre if it == 1 else best_params,
                        scale=self.step_scale * 0.5,
                    )
                else:
                    candidate = self._perturb(centre if it == 1 else best_params)
                metrics = await self.rl_backend._run_simulation_with_params(
                    candidate, mission_conditions, script_path, nmc
                )
                reward = self.rl_backend._compute_reward(metrics)
                fitness = self.rl_backend._compute_pe_fitness(metrics)
                constrained = constraints_satisfied(metrics, reqs)
                _improved = False

                history.append(
                    {
                        "iteration": it,
                        "reward": reward,
                        "fitness": fitness,
                        "metrics": copy.deepcopy(metrics),
                        "params": copy.deepcopy(candidate),
                        "constraints_met": constrained,
                    }
                )

                if episode_logger:
                    episode_logger.write_episode(
                        optimizer="ConstraintLocalSearch",
                        episode=it,
                        params=candidate,
                        metrics=metrics,
                        reward=reward,
                        fitness=fitness,
                        constrained=constrained,
                    )

                sep = metrics.get("SEP", metrics.get("miss_distance", 999.0))
                if isinstance(sep, float) and (math.isnan(sep) or math.isinf(sep)):
                    continue

                # No-regression gate: drop candidates that knock an already-met
                # metric back below its requirement, so satisfied metrics stay
                # satisfied while the search keeps pushing the unmet ones.
                if protect_satisfied and protected_satisfied:
                    _regressed = regressed_satisfied_metrics(
                        best_metrics, metrics, reqs, protected=protected_satisfied
                    )
                    if _regressed:
                        logger.debug(
                            f"  [CLS {it}/{self.max_iterations}] rejected — would break "
                            f"already-met {sorted(_regressed)}"
                        )
                        continue

                if constrained and is_better_constrained(
                    metrics,
                    fitness,
                    best_constrained_metrics,
                    best_constrained_fitness,
                ):
                    best_constrained_params = copy.deepcopy(candidate)
                    best_constrained_metrics = copy.deepcopy(metrics)
                    best_constrained_fitness = fitness
                    _improved = True
                    logger.debug(
                        f"  [CLS {it}/{self.max_iterations}] new constrained best "
                        f"PeakN_max={get_peak_ny_max(metrics):.2f}g SEP={sep:.2f}m "
                        f"fitness={fitness:.4f}"
                    )

                if borderline_select and is_borderline_hit_sep_ok(
                    metrics,
                    hit_min_pct=borderline_hit_min_pct,
                    sep_max_m=borderline_sep_max_m,
                ):
                    if is_better_borderline_peak(metrics, best_borderline_metrics):
                        best_borderline_params = copy.deepcopy(candidate)
                        best_borderline_metrics = copy.deepcopy(metrics)
                        _improved = True
                        logger.debug(
                            f"  [CLS {it}/{self.max_iterations}] new borderline best "
                            f"PeakN_max={get_peak_ny_max(metrics):.2f}g SEP={sep:.2f}m"
                        )

                # Accept as working best if improves fitness or mean peak vs centre
                pny = get_peak_ny(metrics)
                if fitness > best_fitness or (
                    pny > 0
                    and get_peak_ny(best_metrics) > 0
                    and pny < get_peak_ny(best_metrics)
                    and metrics.get("hit_rate", 0) >= best_metrics.get("hit_rate", 0) - 5
                ):
                    best_params = copy.deepcopy(candidate)
                    best_metrics = copy.deepcopy(metrics)
                    best_fitness = fitness
                    _improved = True

                if protect_satisfied:
                    protected_satisfied |= satisfied_metric_keys(best_metrics, reqs)

                _summary = metrics_summary_line(metrics)
                if should_log_cls_step(it, self.max_iterations, improved=_improved):
                    _line = f"  [CLS {it}/{self.max_iterations}] {_summary}"
                    if is_verbose():
                        logger.info(_line)
                    else:
                        logger.info(_line + (" ★" if _improved else ""))
                else:
                    logger.debug(f"  [CLS {it}/{self.max_iterations}] {_summary}")

                if constrained:
                    logger.info(
                        f"[CLS] All constraints satisfied at step {it} — stopping early "
                        f"(PeakN_max={get_peak_ny_max(metrics):.2f}g)"
                    )
                    break

        selection = "center"
        final_params = copy.deepcopy(best_params)
        final_metrics = copy.deepcopy(best_metrics)
        if best_constrained_params and best_constrained_metrics is not None:
            final_params = copy.deepcopy(best_constrained_params)
            final_metrics = copy.deepcopy(best_constrained_metrics)
            selection = "constrained"
        elif (
            borderline_select
            and best_borderline_params
            and best_borderline_metrics is not None
            and is_better_borderline_peak(best_borderline_metrics, final_metrics)
            and not _cls_skip_borderline_for_full_task(task_prompt or "", reqs)
        ):
            final_params = copy.deepcopy(best_borderline_params)
            final_metrics = copy.deepcopy(best_borderline_metrics)
            selection = "borderline"

        logger.info(
            f"[CLS] Done {iterations_run} iterations | selection={selection} | "
            f"PeakN_max={get_peak_ny_max(final_metrics):.2f}g "
            f"SEP={final_metrics.get('SEP', final_metrics.get('miss_distance', 0)):.2f}m"
        )

        return {
            "status": "success",
            "best_params": final_params,
            "best_metrics": final_metrics,
            "best_fitness": best_constrained_fitness if selection == "constrained" else best_fitness,
            "best_constrained_params": best_constrained_params or {},
            "best_constrained_metrics": best_constrained_metrics or {},
            "selection_criteria": selection,
            "total_iterations": iterations_run,
            "history": history[-10:],
        }
