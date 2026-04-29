from __future__ import annotations

import argparse

try:
    from tests.experiments.common import (
        apply_profile,
        restore_config,
        run_once,
        snapshot_config,
        summary,
        write_json,
    )
except ModuleNotFoundError:
    from common import apply_profile, restore_config, run_once, snapshot_config, summary, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="High-load scenario comparison.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[5, 9, 13, 17, 21])
    parser.add_argument("--grid-size", type=int, default=20)
    parser.add_argument("--drivers", type=int, default=12)
    parser.add_argument("--llm-drivers", type=int, default=6)
    parser.add_argument("--steps", type=int, default=220)
    parser.add_argument("--order-prob", type=float, default=0.45)
    parser.add_argument("--strategy", type=str, default="nearest")
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    backup = snapshot_config()
    try:
        baseline_rows = []
        llm_rows = []
        for seed in args.seeds:
            apply_profile(
                grid_size=args.grid_size,
                num_drivers=args.drivers,
                steps=args.steps,
                order_probability=args.order_prob,
                seed=seed,
                strategy=args.strategy,
            )
            baseline_rows.append({"seed": seed, **run_once(use_llm=False, num_llm=0)})
            llm_rows.append({"seed": seed, **run_once(use_llm=True, num_llm=min(args.llm_drivers, args.drivers))})

        keys = [
            "total_orders",
            "completed_orders",
            "completion_rate",
            "total_revenue",
            "avg_waiting_time",
            "max_waiting_time",
            "revenue_gini",
        ]
        payload = {
            "experiment": "high_load_compare",
            "params": vars(args),
            "baseline_rows": baseline_rows,
            "llm_rows": llm_rows,
            "baseline_summary": summary(baseline_rows, keys),
            "llm_summary": summary(llm_rows, keys),
        }
        out = write_json(payload, args.output or None, "exp_04_high_load_compare")
        print(f"saved: {out}")
    finally:
        restore_config(backup)


if __name__ == "__main__":
    main()

