from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ridesim import config  # noqa: E402


class ConfigTestCase(unittest.TestCase):
    """Base testcase that snapshots and restores global config."""

    def setUp(self) -> None:
        self._config_backup = {k: v for k, v in vars(config).items() if k.isupper()}

    def tearDown(self) -> None:
        for key, value in self._config_backup.items():
            setattr(config, key, value)

    def apply_small_fast_config(self, *, seed: int = 42) -> None:
        config.VISUALIZE = False
        config.DEBUG = False
        config.GRID_SIZE = 12
        config.NUM_DRIVERS = 8
        config.SIMULATION_STEPS = 30
        config.ORDER_PROBABILITY = 0.30
        config.RANDOM_SEED = seed
        config.USE_TIME_PERIODS = True
        config.USE_ZONES = True

    def run_simulation_quietly(self, sim) -> None:
        with redirect_stdout(io.StringIO()):
            sim.run()

    def build_simulation_quietly(self):
        from ridesim.simulation import Simulation

        with redirect_stdout(io.StringIO()):
            return Simulation()

