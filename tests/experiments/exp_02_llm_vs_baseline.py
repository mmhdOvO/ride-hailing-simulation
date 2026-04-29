from __future__ import annotations

import argparse

try:
    from tests.experiments.common import (
        apply_profile,
        restore_config,
        run_once,
        snapshot_config,
        write_json,
    )
except ModuleNotFoundError:
    from common import apply_profile, restore_config, run_once, snapshot_config, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-seed LLM vs baseline comparison.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--grid-size", type=int, default=20)
    parser.add_argument("--drivers", type=int, default=20)
    parser.add_argument("--llm-drivers", type=int, default=10)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--order-prob", type=float, default=0.3)
    parser.add_argument("--strategy", type=str, default="nearest")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    backup = snapshot_config()
    try:
        apply_profile(
            grid_size=args.grid_size,
            num_drivers=args.drivers,
            steps=args.steps,
            order_probability=args.order_prob,
            seed=args.seed,
            strategy=args.strategy,
        )

        baseline = run_once(use_llm=False, num_llm=0)
        llm_mix = run_once(use_llm=True, num_llm=min(args.llm_drivers, args.drivers))

        payload = {
            "experiment": "llm_vs_baseline",
            "params": vars(args),
            "baseline": baseline,
            "llm_mix": llm_mix,
            "delta": {
                "completion_rate": llm_mix.get("completion_rate", 0) - baseline.get("completion_rate", 0),
                "total_revenue": llm_mix.get("total_revenue", 0) - baseline.get("total_revenue", 0),
                "avg_waiting_time": llm_mix.get("avg_waiting_time", 0) - baseline.get("avg_waiting_time", 0),
                "revenue_gini": llm_mix.get("revenue_gini", 0) - baseline.get("revenue_gini", 0),
            },
        }
        out = write_json(payload, args.output or None, "exp_02_llm_vs_baseline")
        print(f"saved: {out}")
    finally:
        restore_config(backup)


if __name__ == "__main__":
    main()

