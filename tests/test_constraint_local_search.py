#!/usr/bin/env python3
"""Unit tests for ConstraintLocalSearch (mocked simulation)."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from multi_agent.rl.constraint_local_search import ConstraintLocalSearch
from multi_agent.rl.matlab_rl_optimizer import MatlabRLOptimizer


class TestConstraintLocalSearch(unittest.IsolatedAsyncioTestCase):
    async def test_refine_picks_lower_peak_ny(self):
        backend = MatlabRLOptimizer()
        backend._compute_reward = MagicMock(return_value=0.5)
        backend._compute_pe_fitness = MagicMock(return_value=0.6)

        from multi_agent.rl.matlab_rl_optimizer import ALL_TUNABLE_PARAM_SPECS

        center = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        calls = {"n": 0}

        async def fake_sim(params, mission, script, nmc):
            calls["n"] += 1
            pny = 30.0 if calls["n"] == 1 else 19.0
            return {
                "hit_rate": 100.0,
                "SEP": 5.0,
                "miss_distance": 5.0,
                "peak_ny": pny,
                "peak_ny_max": pny,
                "pitch_PM": 55.0,
                "pitch_BW": 40.0,
            }

        backend._run_simulation_with_params = fake_sim
        backend.extract_params_from_script = MagicMock()

        cls = ConstraintLocalSearch(backend, max_iterations=3, step_scale=0.05, seed=42)
        reqs = {
            "hit_rate_min": 92.0,
            "sep_max": 7.0,
            "peak_ny_max": 20.0,
            "pm_min": 45.0,
            "pm_max": 70.0,
            "bw_min": 20.0,
            "bw_max": 85.0,
        }
        result = await cls.refine(
            center,
            script_path="dummy.m",
            mission_conditions={"T": [4]},
            nmc=5,
            metric_requirements=reqs,
        )
        self.assertEqual(result["selection_criteria"], "constrained")
        self.assertLessEqual(result["best_metrics"].get("peak_ny", 99), 20.0)
        self.assertEqual(result["total_iterations"], 1)
        self.assertEqual(calls["n"], 2)

    async def test_refine_stops_at_center_when_already_satisfied(self):
        backend = MatlabRLOptimizer()
        backend._compute_reward = MagicMock(return_value=0.8)
        backend._compute_pe_fitness = MagicMock(return_value=0.9)

        from multi_agent.rl.matlab_rl_optimizer import ALL_TUNABLE_PARAM_SPECS

        center = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        calls = {"n": 0}

        async def fake_sim(params, mission, script, nmc):
            calls["n"] += 1
            return {
                "hit_rate": 100.0,
                "SEP": 5.0,
                "miss_distance": 5.0,
                "peak_ny": 18.0,
                "peak_ny_max": 19.5,
                "pitch_PM": 55.0,
                "pitch_BW": 40.0,
            }

        backend._run_simulation_with_params = fake_sim
        backend.extract_params_from_script = MagicMock()

        cls = ConstraintLocalSearch(backend, max_iterations=50, step_scale=0.05, seed=42)
        reqs = {
            "hit_rate_min": 92.0,
            "sep_max": 7.0,
            "peak_ny_max": 20.0,
            "pm_min": 45.0,
            "pm_max": 70.0,
            "bw_min": 20.0,
            "bw_max": 85.0,
        }
        result = await cls.refine(
            center,
            script_path="dummy.m",
            mission_conditions={"T": [4]},
            nmc=5,
            metric_requirements=reqs,
        )
        self.assertEqual(result["selection_criteria"], "constrained")
        self.assertEqual(result["total_iterations"], 0)
        self.assertEqual(calls["n"], 1)

    async def test_refine_skips_borderline_when_five_metrics_required(self):
        backend = MatlabRLOptimizer()
        backend._compute_reward = MagicMock(return_value=0.5)
        backend._compute_pe_fitness = MagicMock(return_value=0.6)

        from multi_agent.rl.matlab_rl_optimizer import ALL_TUNABLE_PARAM_SPECS

        center = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        calls = {"n": 0}

        async def fake_sim(params, mission, script, nmc):
            calls["n"] += 1
            return {
                "hit_rate": 100.0,
                "SEP": 5.0,
                "miss_distance": 5.0,
                "peak_ny": 19.0,
                "peak_ny_max": 19.5,
                "pitch_PM": 55.0,
                "pitch_BW": 110.0,
            }

        backend._run_simulation_with_params = fake_sim
        backend.extract_params_from_script = MagicMock()

        cls = ConstraintLocalSearch(backend, max_iterations=2, step_scale=0.05, seed=42)
        task_prompt = (
            "命中率 >= 92% SEP <= 7 m PeakNy <= 20 g "
            "PM 在 45°~70° BW 在 20~85 rad/s"
        )
        result = await cls.refine(
            center,
            script_path="dummy.m",
            mission_conditions={"T": [4]},
            nmc=5,
            task_prompt=task_prompt,
        )
        self.assertNotEqual(result["selection_criteria"], "borderline")
        self.assertGreater(result["best_metrics"].get("pitch_BW", 0), 85.0)

    def _peak_only_unmet_backend(self):
        """Center meets hit/SEP/PM/BW (peak unmet); every candidate fixes peak
        but breaks PM. Returns (backend, center, reqs, calls)."""
        backend = MatlabRLOptimizer()
        backend._compute_reward = MagicMock(return_value=0.5)
        backend._compute_pe_fitness = MagicMock(return_value=0.6)

        from multi_agent.rl.matlab_rl_optimizer import ALL_TUNABLE_PARAM_SPECS

        center = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        calls = {"n": 0}

        async def fake_sim(params, mission, script, nmc):
            calls["n"] += 1
            if calls["n"] == 1:  # center: peak too high, PM/BW/hit/SEP all OK
                return {
                    "hit_rate": 100.0, "SEP": 5.0, "miss_distance": 5.0,
                    "peak_ny": 25.0, "peak_ny_max": 25.0,
                    "pitch_PM": 60.0, "pitch_BW": 40.0,
                }
            # candidates: peak now OK but PM dropped below the 45 floor
            return {
                "hit_rate": 100.0, "SEP": 5.0, "miss_distance": 5.0,
                "peak_ny": 18.0, "peak_ny_max": 18.0,
                "pitch_PM": 40.0, "pitch_BW": 40.0,
            }

        backend._run_simulation_with_params = fake_sim
        backend.extract_params_from_script = MagicMock()
        reqs = {
            "hit_rate_min": 92.0, "sep_max": 7.0, "peak_ny_max": 20.0,
            "pm_min": 45.0, "pm_max": 70.0, "bw_min": 20.0, "bw_max": 85.0,
        }
        return backend, center, reqs, calls

    async def test_protect_satisfied_rejects_metric_regression(self):
        """A candidate that fixes the unmet metric but breaks an already-met one
        is rejected, so the working best keeps the satisfied metric."""
        backend, center, reqs, _ = self._peak_only_unmet_backend()
        cls = ConstraintLocalSearch(backend, max_iterations=3, step_scale=0.05, seed=42)
        result = await cls.refine(
            center, script_path="dummy.m", mission_conditions={"T": [4]},
            nmc=5, metric_requirements=reqs, protect_satisfied=True,
        )
        # All PM-breaking candidates rejected → no fully-constrained pick, PM held.
        self.assertNotEqual(result["selection_criteria"], "constrained")
        self.assertGreaterEqual(result["best_metrics"].get("pitch_PM", 0.0), 45.0)

    async def test_protect_satisfied_off_allows_regression(self):
        """With the gate disabled, the peak-improving candidate is adopted even
        though it breaks PM — reproduces the original 'satisfied → unsatisfied'."""
        backend, center, reqs, _ = self._peak_only_unmet_backend()
        cls = ConstraintLocalSearch(backend, max_iterations=3, step_scale=0.05, seed=42)
        result = await cls.refine(
            center, script_path="dummy.m", mission_conditions={"T": [4]},
            nmc=5, metric_requirements=reqs, protect_satisfied=False,
        )
        self.assertLess(result["best_metrics"].get("pitch_PM", 99.0), 45.0)

    def _peak_descent_backend(self):
        """Center meets hit/SEP/PM/BW with PeakNy_avg unmet (23.3g). Candidates:
        a high-fitness/high-peak point (lower SEP), then a low-peak point (higher
        SEP), then high-fitness/high-peak again — mirroring the real run where the
        blended fitness pulls the working best toward polishing already-satisfied
        SEP at the cost of PeakNy. Fitness rises as SEP falls.
        """
        backend = MatlabRLOptimizer()
        backend._compute_reward = MagicMock(return_value=0.5)
        backend._compute_pe_fitness = (
            lambda m: 1.0 / (1.0 + float(m.get("SEP", m.get("miss_distance", 100.0))))
        )

        from multi_agent.rl.matlab_rl_optimizer import ALL_TUNABLE_PARAM_SPECS

        center = {k: float(v["nominal"]) for k, v in ALL_TUNABLE_PARAM_SPECS.items()}
        calls = {"n": 0}
        # (peak_ny, SEP) by call: center, then three candidates.
        seq = [(23.3, 5.0), (24.0, 4.0), (21.0, 6.5), (24.5, 4.0)]

        async def fake_sim(params, mission, script, nmc):
            calls["n"] += 1
            pny, sep = seq[min(calls["n"] - 1, len(seq) - 1)]
            return {
                "hit_rate": 100.0, "SEP": sep, "miss_distance": sep,
                "peak_ny": pny, "peak_ny_max": pny,
                "pitch_PM": 55.0, "pitch_BW": 40.0,
            }

        backend._run_simulation_with_params = fake_sim
        backend.extract_params_from_script = MagicMock()
        # Full five-metric optimization prompt → borderline pick is skipped, so the
        # final selection is the working best (the bug surfaces here, not via the
        # independent borderline tracker).
        task_prompt = (
            "命中率 >= 92% SEP <= 7 m PeakNy <= 20 g "
            "PM 在 45°~70° BW 在 20~85 rad/s"
        )
        return backend, center, task_prompt, calls

    async def test_protect_satisfied_descends_unmet_peak(self):
        """Only PeakNy_avg unmet: the working best must track the lowest-peak
        feasible candidate (21.0g), not drift to the higher-fitness/higher-peak
        one — i.e. PeakNy_avg is actually reduced below the center while the other
        four metrics stay satisfied."""
        backend, center, task_prompt, _ = self._peak_descent_backend()
        cls = ConstraintLocalSearch(backend, max_iterations=3, step_scale=0.05, seed=7)
        result = await cls.refine(
            center, script_path="dummy.m", mission_conditions={"T": [4]},
            nmc=5, task_prompt=task_prompt, protect_satisfied=True,
        )
        self.assertNotEqual(result["selection_criteria"], "borderline")
        # PeakNy reduced below the center (23.3g) — the lowest feasible peak found.
        self.assertLessEqual(result["best_metrics"].get("peak_ny", 99.0), 21.0)
        # The already-satisfied metrics are still satisfied.
        self.assertGreaterEqual(result["best_metrics"].get("pitch_PM", 0.0), 45.0)
        self.assertLessEqual(result["best_metrics"].get("pitch_PM", 0.0), 70.0)
        self.assertGreaterEqual(result["best_metrics"].get("pitch_BW", 0.0), 20.0)

    async def test_fitness_drift_without_protect_descent(self):
        """Reproduces the bug: with the no-regression gate off, the working best is
        chosen by blended fitness and drifts to the high-fitness/high-peak point,
        so PeakNy_avg is NOT reduced (ends at/above the center)."""
        backend, center, task_prompt, _ = self._peak_descent_backend()
        cls = ConstraintLocalSearch(backend, max_iterations=3, step_scale=0.05, seed=7)
        result = await cls.refine(
            center, script_path="dummy.m", mission_conditions={"T": [4]},
            nmc=5, task_prompt=task_prompt, protect_satisfied=False,
        )
        self.assertGreaterEqual(result["best_metrics"].get("peak_ny", 0.0), 24.0)


if __name__ == "__main__":
    unittest.main()
