from __future__ import annotations

import unittest

from tests.health.test_00_common import ConfigTestCase


class TestSmokeRun(ConfigTestCase):
    def test_run_without_llm_completes_and_has_basic_stats(self) -> None:
        self.apply_small_fast_config(seed=11)
        from ridesim import config

        config.USE_LLM_DRIVERS = False
        sim = self.build_simulation_quietly()
        self.run_simulation_quietly(sim)
        stats = sim.collect_statistics()

        self.assertEqual(sim.current_step, config.SIMULATION_STEPS)
        self.assertGreaterEqual(stats["total_orders"], stats["completed_orders"])
        self.assertGreaterEqual(stats["completion_rate"], 0.0)
        self.assertLessEqual(stats["completion_rate"], 100.0)
        self.assertEqual(len(stats["driver_stats"]), config.NUM_DRIVERS)


if __name__ == "__main__":
    unittest.main()

