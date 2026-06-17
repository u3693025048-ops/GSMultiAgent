"""Multi-criteria metric constraints for RL / local search selection."""

from __future__ import annotations

from typing import Any, Dict, Optional, Set, Tuple

from multi_agent.integration.judgment_agent import _rule_based_check
from multi_agent.rl.metric_utils import (
    get_peak_ny,
    get_peak_ny_limit,
    get_peak_ny_max,
    get_sep,
)

# Canonical metric keys used by the per-metric satisfaction map.
METRIC_KEYS: Tuple[str, ...] = (
    "hit_rate",
    "SEP",
    "peak_ny",
    "pitch_PM",
    "pitch_BW",
)


def constraints_satisfied(
    metrics: Dict[str, float],
    reqs: Dict[str, Any],
    task_prompt: str = "",
) -> bool:
    """True when all parsed task requirements are met."""
    from multi_agent.integration.judgment_agent import all_requirements_satisfied

    return all_requirements_satisfied(metrics, reqs, task_prompt)


def constrained_rank_key(
    metrics: Dict[str, float],
    fitness: float = 0.0,
) -> Tuple[float, float, float, float]:
    """Sort key for constrained candidates — lower is better.

    Priority: mean overshoot → SEP → fitness (negated).
    """
    mean_max = get_peak_ny_limit({})
    pny_mean = get_peak_ny(metrics)
    if pny_mean <= 0:
        pny_mean = 1e6
    mean_over = max(0.0, pny_mean - mean_max)
    sep = get_sep(metrics, 1e6)
    return (mean_over, sep, -float(fitness))


def is_better_constrained(
    metrics_a: Dict[str, float],
    fitness_a: float,
    metrics_b: Optional[Dict[str, float]],
    fitness_b: float,
) -> bool:
    """Return True if *a* strictly dominates *b* under constrained rank."""
    if metrics_b is None:
        return True
    return constrained_rank_key(metrics_a, fitness_a) < constrained_rank_key(
        metrics_b, fitness_b
    )


def is_borderline_hit_sep_ok(
    metrics: Dict[str, float],
    *,
    hit_min_pct: float = 92.0,
    sep_max_m: float = 7.0,
) -> bool:
    """True when hit/SEP meet requirements (peak/PM/BW may still fail)."""
    try:
        hit = float(metrics.get("hit_rate") or 0.0)
    except (TypeError, ValueError):
        hit = 0.0
    sep = get_sep(metrics, 1e6)
    if hit < hit_min_pct:
        return False
    if sep > sep_max_m:
        return False
    return True


def should_adopt_cls_result(
    prior_metrics: Optional[Dict[str, float]],
    prior_fitness: float,
    cls_metrics: Optional[Dict[str, float]],
    cls_fitness: float,
    *,
    reqs: Optional[Dict[str, Any]] = None,
    task_prompt: str = "",
) -> bool:
    """True when CLS output should replace Expert/PPO best (mean-based rank, not peak_max)."""
    if not cls_metrics:
        return False
    if not prior_metrics:
        return True
    if reqs and constraints_satisfied(cls_metrics, reqs, task_prompt):
        return True
    if reqs and constraints_satisfied(prior_metrics, reqs, task_prompt):
        return False
    return is_better_constrained(cls_metrics, cls_fitness, prior_metrics, prior_fitness)


def is_better_borderline_peak(
    metrics_a: Dict[str, float],
    metrics_b: Optional[Dict[str, float]],
) -> bool:
    """Lower mean peak then SEP wins among borderline hit/SEP-ok candidates."""
    if metrics_b is None:
        return True
    mean_a = get_peak_ny(metrics_a)
    mean_b = get_peak_ny(metrics_b)
    if mean_a != mean_b:
        return mean_a < mean_b
    return get_sep(metrics_a, 1e6) < get_sep(metrics_b, 1e6)


def resolve_requirements(
    metric_requirements: Optional[Dict[str, Any]],
    task_prompt: Optional[str],
    judgment_agent: Any = None,
) -> Dict[str, Any]:
    """Merge explicit requirements with JudgmentAgent / prompt parsing."""
    from multi_agent.rl.metric_utils import normalize_peak_ny_requirements

    from multi_agent.integration.judgment_agent import (
        merge_requirements,
        resolve_task_requirements,
    )

    if metric_requirements:
        base = (
            resolve_task_requirements(task_prompt or "", judgment_agent)
            if task_prompt
            else {}
        )
        return merge_requirements(base, metric_requirements)
    if task_prompt:
        return resolve_task_requirements(task_prompt, judgment_agent)
    if judgment_agent is not None and getattr(judgment_agent, "_reqs", None):
        return normalize_peak_ny_requirements(dict(judgment_agent._reqs))
    return normalize_peak_ny_requirements({})


def per_metric_satisfied(
    metrics: Dict[str, float],
    reqs: Dict[str, Any],
) -> Dict[str, bool]:
    """Per-metric pass/fail for every metric that has a stated requirement.

    Returns a dict keyed by canonical metric name (subset of ``METRIC_KEYS``)
    mapping to whether that single metric meets its requirement. Metrics with
    no stated requirement are omitted, so callers can treat "missing" as
    "unconstrained". Bound semantics mirror ``judgment_agent._rule_based_check``.
    """
    if not reqs:
        return {}

    out: Dict[str, bool] = {}

    if "hit_rate_min" in reqs:
        hr = metrics.get("hit_rate", 0.0)
        out["hit_rate"] = hr >= reqs["hit_rate_min"]

    if "sep_max" in reqs:
        out["SEP"] = get_sep(metrics, 999.0) <= reqs["sep_max"]

    if "peak_ny_max" in reqs or "peak_ny_mean_max" in reqs:
        from multi_agent.rl.metric_utils import (
            check_peak_ny,
            normalize_peak_ny_requirements,
        )

        ok_peak, _ = check_peak_ny(metrics, normalize_peak_ny_requirements(reqs))
        out["peak_ny"] = ok_peak

    if "pm_min" in reqs:
        pm = metrics.get("pitch_PM", 0.0)
        if "pm_max" in reqs:
            out["pitch_PM"] = reqs["pm_min"] <= pm <= reqs["pm_max"]
        else:
            out["pitch_PM"] = pm >= reqs["pm_min"]

    if "bw_min" in reqs and "bw_max" in reqs:
        bw = metrics.get("pitch_BW", 0.0)
        out["pitch_BW"] = reqs["bw_min"] <= bw <= reqs["bw_max"]

    return out


def satisfied_metric_keys(
    metrics: Dict[str, float],
    reqs: Dict[str, Any],
) -> Set[str]:
    """Set of metric keys that individually meet their requirement."""
    return {k for k, ok in per_metric_satisfied(metrics, reqs).items() if ok}


def regressed_satisfied_metrics(
    baseline_metrics: Dict[str, float],
    candidate_metrics: Dict[str, float],
    reqs: Dict[str, Any],
    *,
    protected: Optional[Set[str]] = None,
) -> Set[str]:
    """Metrics that were satisfied (in baseline / ``protected``) but fail in candidate.

    ``protected`` overrides the baseline-derived satisfied set when given, which
    lets callers carry a monotonically-growing set of metrics that must stay
    satisfied across iterations.
    """
    base_sat = protected if protected is not None else satisfied_metric_keys(
        baseline_metrics, reqs
    )
    if not base_sat:
        return set()
    cand_sat = satisfied_metric_keys(candidate_metrics, reqs)
    return set(base_sat) - cand_sat


def no_satisfied_regression(
    baseline_metrics: Dict[str, float],
    candidate_metrics: Dict[str, float],
    reqs: Dict[str, Any],
    *,
    protected: Optional[Set[str]] = None,
) -> bool:
    """True when the candidate keeps every already-satisfied metric satisfied."""
    return not regressed_satisfied_metrics(
        baseline_metrics, candidate_metrics, reqs, protected=protected
    )
