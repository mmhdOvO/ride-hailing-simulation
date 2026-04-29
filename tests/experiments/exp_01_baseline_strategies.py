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
    parser = argparse.ArgumentParser(description="Compare baseline driver strategies.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--grid-size", type=int, default=20)
    parser.add_argument("--drivers", type=int, default=20)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--order-prob", type=float, default=0.3)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    backup = snapshot_config()
    try:
        rows = []
        for strategy in ("nearest", "random", "round_robin"):
            apply_profile(
                grid_size=args.grid_size,
                num_drivers=args.drivers,
                steps=args.steps,
                order_probability=args.order_prob,
                seed=args.seed,
                strategy=strategy,
            )
            stats = run_once(use_llm=False, num_llm=0)
            rows.append({"strategy": strategy, **stats})

        payload = {
            "experiment": "baseline_strategies",
            "params": vars(args),
            "rows": rows,
        }
        out = write_json(payload, args.output or None, "exp_01_baseline_strategies")
        print(f"saved: {out}")
    finally:
        restore_config(backup)


if __name__ == "__main__":
    main()

