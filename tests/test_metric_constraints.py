#!/usr/bin/env python3
"""Tests for multi-criteria constraint selection."""

import unittest

from multi_agent.rl.metric_constraints import (
    constrained_rank_key,
    constraints_satisfied,
    is_better_constrained,
    should_adopt_cls_result,
)
from multi_agent.rl.metric_utils import get_peak_ny_max


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


if __name__ == "__main__":
    unittest.main()
