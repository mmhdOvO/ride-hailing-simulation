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
    parser = argparse.ArgumentParser(description="Multi-seed comparison: baseline vs llm mix.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[3, 7, 11, 19, 29])
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
            "completion_rate",
            "total_revenue",
            "avg_waiting_time",
            "max_waiting_time",
            "revenue_gini",
            "revenue_cv",
        ]
        payload = {
            "experiment": "multi_seed_compare",
            "params": vars(args),
            "baseline_rows": baseline_rows,
            "llm_rows": llm_rows,
            "baseline_summary": summary(baseline_rows, keys),
            "llm_summary": summary(llm_rows, keys),
        }
        out = write_json(payload, args.output or None, "exp_03_multi_seed_compare")
        print(f"saved: {out}")
    finally:
        restore_config(backup)


if __name__ == "__main__":
    main()

