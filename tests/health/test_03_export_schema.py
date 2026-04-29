from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tests.health.test_00_common import ConfigTestCase


class TestExportSchema(ConfigTestCase):
    def test_export_contains_required_top_level_keys(self) -> None:
        self.apply_small_fast_config(seed=31)
        from ridesim import config

        config.USE_LLM_DRIVERS = False
        sim = self.build_simulation_quietly()
        self.run_simulation_quietly(sim)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "run_export.json"
            with redirect_stdout(io.StringIO()):
                sim.export_data(str(out_path))
            self.assertTrue(out_path.exists())

            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("config", payload)
            self.assertIn("statistics", payload)
            self.assertIn("final_state", payload)
            self.assertIn("drivers", payload["final_state"])
            self.assertIn("orders", payload["final_state"])


if __name__ == "__main__":
    unittest.main()

