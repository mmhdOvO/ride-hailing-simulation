from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ridesim import config  # noqa: E402


def snapshot_config() -> dict:
    return {k: v for k, v in vars(config).items() if k.isupper()}


def restore_config(cfg: dict) -> None:
    for key, value in cfg.items():
        setattr(config, key, value)


def apply_profile(
    *,
    grid_size: int,
    num_drivers: int,
    steps: int,
    order_probability: float,
    seed: int,
    strategy: str = "nearest",
) -> None:
    config.VISUALIZE = False
    config.DEBUG = False
    config.GRID_SIZE = grid_size
    config.NUM_DRIVERS = num_drivers
    config.SIMULATION_STEPS = steps
    config.ORDER_PROBABILITY = order_probability
    config.RANDOM_SEED = seed
    config.NORMAL_STRATEGY = strategy


def run_once(*, use_llm: bool, num_llm: int) -> dict:
    from ridesim.simulation import Simulation

    config.USE_LLM_DRIVERS = use_llm
    config.NUM_LLM_DRIVERS = num_llm
    sim = Simulation()
    sim.run()
    return sim.collect_statistics()


def summary(rows: list[dict], keys: list[str]) -> dict:
    agg = {}
    for k in keys:
        vals = [r[k] for r in rows if k in r]
        if not vals:
            continue
        agg[k] = {"mean": mean(vals), "std": pstdev(vals) if len(vals) > 1 else 0.0}
    return agg


def write_json(payload: dict, output: str | None, default_name: str) -> Path:
    output_dir = ROOT / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    if output:
        out = Path(output)
        if not out.is_absolute():
            out = ROOT / output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = output_dir / f"{default_name}_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

