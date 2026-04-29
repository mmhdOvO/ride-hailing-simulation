from __future__ import annotations

import unittest

from tests.health.test_00_common import ConfigTestCase


class TestDispatchStrategies(ConfigTestCase):
    def _run_one(self, strategy: str, seed: int = 23) -> dict:
        self.apply_small_fast_config(seed=seed)
        from ridesim import config

        config.USE_LLM_DRIVERS = False
        config.NORMAL_STRATEGY = strategy
        sim = self.build_simulation_quietly()
        self.run_simulation_quietly(sim)
        return sim.collect_statistics()

    def test_all_builtin_strategies_are_executable(self) -> None:
        for strategy in ("nearest", "random", "round_robin"):
            with self.subTest(strategy=strategy):
                stats = self._run_one(strategy=strategy, seed=23)
                self.assertGreaterEqual(stats["total_orders"], 0)
                self.assertGreaterEqual(stats["completed_orders"], 0)
                self.assertGreaterEqual(stats["total_revenue"], 0)


if __name__ == "__main__":
    unittest.main()

