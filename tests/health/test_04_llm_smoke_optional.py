from __future__ import annotations

import os
import unittest

from tests.health.test_00_common import ConfigTestCase
from ridesim.utils import driver as drv


@unittest.skipUnless(os.getenv("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY not set")
class TestLLMSmokeOptional(ConfigTestCase):
    def test_mixed_fleet_runs_with_llm_enabled(self) -> None:
        self.apply_small_fast_config(seed=41)
        from ridesim import config

        config.USE_LLM_DRIVERS = True
        config.NUM_LLM_DRIVERS = 2
        config.API_TIMEOUT = 8
        config.MAX_API_RETRIES = 1

        sim = self.build_simulation_quietly()
        self.run_simulation_quietly(sim)
        stats = sim.collect_statistics()

        llm_count = sum(1 for d in sim.drivers if drv.is_llm(d))
        self.assertEqual(llm_count, 2)
        self.assertGreaterEqual(stats["completed_orders"], 0)


if __name__ == "__main__":
    unittest.main()

