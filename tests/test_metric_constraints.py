#!/usr/bin/env python3
"""Tests for multi-criteria constraint selection."""

import unittest

from multi_agent.rl.metric_constraints import (
    constrained_rank_key,
    constraints_satisfied,
    is_better_constrained,
    no_satisfied_regression,
    per_metric_satisfied,
    regressed_satisfied_metrics,
    satisfied_metric_keys,
    should_adopt_cls_result,
)
from multi_agent.rl.metric_utils import get_peak_ny_max

FULL_REQS = {
    "hit_rate_min": 92.0,
    "sep_max": 7.0,
    "peak_ny_max": 20.0,
    "pm_min": 45.0,
    "pm_max": 70.0,
    "bw_min": 20.0,
    "bw_max": 85.0,
}


class TestMetricConstraints(unittest.TestCase):
    def test_constraints_satisfied_all_ok(self):
        metrics = {
            "hit_rate": 100.0,
            "SEP": 4.5,
            "peak_ny": 18.0,
            "peak_ny_max": 19.0,
            "pitch_PM": 60.0,
            "pitch_BW": 40.0,
        }
        reqs = {
            "hit_rate_min": 92.0,
            "sep_max": 7.0,
            "peak_ny_max": 20.0,
            "pm_min": 45.0,
            "pm_max": 70.0,
            "bw_min": 20.0,
            "bw_max": 85.0,
        }
        self.assertTrue(constraints_satisfied(metrics, reqs))

    def test_constraints_pass_when_max_over_but_mean_ok(self):
        metrics = {
            "hit_rate": 100.0,
            "SEP": 4.5,
            "peak_ny": 17.0,
            "peak_ny_max": 25.0,
            "pitch_PM": 60.0,
            "pitch_BW": 40.0,
        }
        reqs = {"hit_rate_min": 92.0, "sep_max": 7.0, "peak_ny_max": 20.0}
        self.assertTrue(constraints_satisfied(metrics, reqs))

    def test_peak_ny_pass_mean_only(self):
        """v20 CLS-7 style: mean<=20 satisfies even if max>21."""
        metrics = {
            "hit_rate": 100.0,
            "SEP": 4.98,
            "peak_ny": 17.86,
            "peak_ny_max": 20.35,
            "pitch_PM": 52.3,
            "pitch_BW": 76.5,
        }
        reqs = {
            "hit_rate_min": 92.0,
            "sep_max": 7.0,
            "peak_ny_max": 20.0,
            "peak_ny_mean_max": 20.0,
            "pm_min": 45.0,
            "pm_max": 70.0,
            "bw_min": 20.0,
            "bw_max": 85.0,
        }
        self.assertTrue(constraints_satisfied(metrics, reqs))

    def test_get_peak_ny_max_prefers_max_key(self):
        m = {"peak_ny": 17.0, "peak_ny_max": 27.37}
        self.assertAlmostEqual(get_peak_ny_max(m), 27.37)

    def test_is_better_constrained_prefers_lower_peak_ny(self):
        a = {"peak_ny_max": 18.0, "peak_ny": 18.0, "SEP": 5.0, "miss_distance": 5.0}
        b = {"peak_ny_max": 24.0, "peak_ny": 24.0, "SEP": 4.0, "miss_distance": 4.0}
        self.assertTrue(is_better_constrained(a, 0.8, b, 0.9))

    def test_constrained_rank_key_order(self):
        low = constrained_rank_key({"peak_ny_max": 15.0, "peak_ny": 15.0, "SEP": 5.0}, 0.5)
        high = constrained_rank_key({"peak_ny_max": 30.0, "peak_ny": 30.0, "SEP": 4.0}, 0.9)
        self.assertLess(low, high)

    def test_should_adopt_cls_iter1_mean_beats_max(self):
        """CLS SEP/mean win even when peak_ny_max is slightly higher than PPO."""
        prior = {
            "hit_rate": 96.0,
            "SEP": 11.32,
            "peak_ny": 21.55,
            "peak_ny_max": 25.44,
            "pitch_PM": 69.2,
            "pitch_BW": 88.62,
        }
        cls = {
            "hit_rate": 100.0,
            "SEP": 4.98,
            "peak_ny": 20.65,
            "peak_ny_max": 26.30,
            "pitch_PM": 54.7,
            "pitch_BW": 84.2,
        }
        reqs = {
            "hit_rate_min": 92.0,
            "sep_max": 7.0,
            "peak_ny_max": 20.0,
            "pm_min": 45.0,
            "pm_max": 70.0,
            "bw_min": 20.0,
            "bw_max": 85.0,
        }
        self.assertTrue(
            should_adopt_cls_result(prior, 0.5, cls, 0.6, reqs=reqs, task_prompt="PeakNy")
        )


class TestNoSatisfiedRegression(unittest.TestCase):
    """Per-metric satisfaction and the no-regression gate (option 1)."""

    def test_per_metric_satisfied_mixed(self):
        metrics = {
            "hit_rate": 100.0,   # OK
            "SEP": 9.0,          # NG (>7)
            "peak_ny": 18.0,     # OK
            "pitch_PM": 40.0,    # NG (<45)
            "pitch_BW": 40.0,    # OK
        }
        result = per_metric_satisfied(metrics, FULL_REQS)
        self.assertEqual(
            result,
            {
                "hit_rate": True,
                "SEP": False,
                "peak_ny": True,
                "pitch_PM": False,
                "pitch_BW": True,
            },
        )
        self.assertEqual(
            satisfied_metric_keys(metrics, FULL_REQS),
            {"hit_rate", "peak_ny", "pitch_BW"},
        )

    def test_per_metric_only_stated_requirements(self):
        # Only hit + SEP stated → other metrics are unconstrained / omitted.
        reqs = {"hit_rate_min": 92.0, "sep_max": 7.0}
        metrics = {"hit_rate": 95.0, "SEP": 8.0, "pitch_PM": 10.0}
        self.assertEqual(
            per_metric_satisfied(metrics, reqs), {"hit_rate": True, "SEP": False}
        )

    def test_no_requirements_is_unprotected(self):
        # Empty reqs → nothing protected → never a regression (original behaviour).
        self.assertEqual(satisfied_metric_keys({"hit_rate": 100.0}, {}), set())
        self.assertTrue(no_satisfied_regression({"pitch_PM": 60.0}, {"pitch_PM": 0.0}, {}))

    def test_regression_detected_when_met_metric_breaks(self):
        baseline = {
            "hit_rate": 100.0, "SEP": 5.0, "peak_ny": 25.0,
            "pitch_PM": 60.0, "pitch_BW": 40.0,
        }  # peak unmet, PM/BW/hit/SEP met
        candidate = {
            "hit_rate": 100.0, "SEP": 5.0, "peak_ny": 18.0,
            "pitch_PM": 40.0, "pitch_BW": 40.0,
        }  # fixes peak but breaks PM
        self.assertEqual(
            regressed_satisfied_metrics(baseline, candidate, FULL_REQS), {"pitch_PM"}
        )
        self.assertFalse(no_satisfied_regression(baseline, candidate, FULL_REQS))

    def test_no_regression_when_unmet_metric_improves(self):
        baseline = {
            "hit_rate": 100.0, "SEP": 5.0, "peak_ny": 25.0,
            "pitch_PM": 60.0, "pitch_BW": 40.0,
        }
        candidate = {  # fixes peak, keeps everything else satisfied
            "hit_rate": 100.0, "SEP": 5.0, "peak_ny": 18.0,
            "pitch_PM": 60.0, "pitch_BW": 40.0,
        }
        self.assertTrue(no_satisfied_regression(baseline, candidate, FULL_REQS))

    def test_protected_set_overrides_baseline(self):
        # Even if baseline no longer satisfies PM, an explicit protected set holds.
        baseline = {"pitch_PM": 40.0}
        candidate = {"pitch_PM": 40.0}
        self.assertEqual(
            regressed_satisfied_metrics(
                baseline, candidate, FULL_REQS, protected={"pitch_PM"}
            ),
            {"pitch_PM"},
        )


if __name__ == "__main__":
    unittest.main()
