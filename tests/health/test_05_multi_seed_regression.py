from __future__ import annotations

import statistics
import unittest

from tests.health.test_00_common import ConfigTestCase


class TestMultiSeedRegression(ConfigTestCase):
    def _run_once(self, seed: int) -> dict:
        self.apply_small_fast_config(seed=seed)
        from ridesim import config

        config.USE_LLM_DRIVERS = False
        config.NORMAL_STRATEGY = "nearest"
        sim = self.build_simulation_quietly()
        self.run_simulation_quietly(sim)
        return sim.collect_statistics()

    def test_multi_seed_completion_rate_is_stable(self) -> None:
        rates = []
        revenues = []
        for seed in (3, 7, 11, 19, 29):
            stats = self._run_once(seed)
            rates.append(stats["completion_rate"])
            revenues.append(stats["total_revenue"])

        self.assertGreater(statistics.mean(rates), 5.0)
        self.assertGreater(statistics.mean(revenues), 0.0)
        self.assertLess(statistics.pstdev(rates), 35.0)


if __name__ == "__main__":
    unittest.main()

