from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "tests" / "output"

METRIC_ZH = {
    "total_orders": "总订单数",
    "completed_orders": "完成订单数",
    "completion_rate": "完成率(%)",
    "total_revenue": "总收入(元)",
    "avg_waiting_time": "平均等待步数",
    "max_waiting_time": "最长等待步数",
    "revenue_gini": "收入基尼系数",
    "revenue_cv": "收入变异系数",
}

STRATEGY_ZH = {
    "nearest": "最近优先",
    "random": "随机",
    "round_robin": "轮询",
}


def _fmt(value) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _extract_summary(payload: dict, side: str, metric: str) -> str:
    block = payload.get(side, {})
    item = block.get(metric)
    if isinstance(item, dict) and "mean" in item:
        mean = item["mean"]
        std = item.get("std", 0.0)
        return f"{_fmt(mean)} ± {_fmt(std)}"
    if item is None:
        return "-"
    return _fmt(item)


def _render_multi_seed_table(payload: dict) -> str:
    metrics = [
        "completion_rate",
        "total_revenue",
        "avg_waiting_time",
        "max_waiting_time",
        "revenue_gini",
        "revenue_cv",
    ]
    lines = [
        "### 多随机种子对比",
        "",
        "| 指标 | 传统策略 (均值±标准差) | LLM混合策略 (均值±标准差) |",
        "|---|---:|---:|",
    ]
    for m in metrics:
        b = _extract_summary(payload, "baseline_summary", m)
        l = _extract_summary(payload, "llm_summary", m)
        lines.append(f"| {METRIC_ZH.get(m, m)} | {b} | {l} |")
    return "\n".join(lines)


def _render_high_load_table(payload: dict) -> str:
    metrics = [
        "total_orders",
        "completed_orders",
        "completion_rate",
        "total_revenue",
        "avg_waiting_time",
        "max_waiting_time",
        "revenue_gini",
    ]
    lines = [
        "### 高负载场景对比",
        "",
        "| 指标 | 传统策略 (均值±标准差) | LLM混合策略 (均值±标准差) |",
        "|---|---:|---:|",
    ]
    for m in metrics:
        b = _extract_summary(payload, "baseline_summary", m)
        l = _extract_summary(payload, "llm_summary", m)
        lines.append(f"| {METRIC_ZH.get(m, m)} | {b} | {l} |")
    return "\n".join(lines)


def _render_single_table(payload: dict) -> str:
    baseline = payload.get("baseline", {})
    llm = payload.get("llm_mix", {})
    metrics = [
        "completion_rate",
        "total_revenue",
        "avg_waiting_time",
        "max_waiting_time",
        "revenue_gini",
    ]
    lines = [
        "### 单次实验对比",
        "",
        "| 指标 | 传统策略 | LLM混合策略 |",
        "|---|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            f"| {METRIC_ZH.get(m, m)} | {_fmt(baseline.get(m, '-'))} | {_fmt(llm.get(m, '-'))} |"
        )
    return "\n".join(lines)


def _render_baseline_strategies_table(payload: dict) -> str:
    rows = payload.get("rows", [])
    metrics = [
        "completed_orders",
        "completion_rate",
        "total_revenue",
        "avg_waiting_time",
        "max_waiting_time",
        "revenue_gini",
    ]
    lines = [
        "### Baseline 策略对比",
        "",
        "| 策略 | 完成订单数 | 完成率(%) | 总收入(元) | 平均等待步数 | 最长等待步数 | 收入基尼系数 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        strategy = row.get("strategy", "-")
        values = [_fmt(row.get(m, "-")) for m in metrics]
        lines.append(f"| {STRATEGY_ZH.get(strategy, strategy)} | " + " | ".join(values) + " |")
    return "\n".join(lines)


def render_markdown(payload: dict, source_name: str) -> str:
    exp = payload.get("experiment", "unknown")
    lines = [f"## 实验报告：`{source_name}`", ""]
    if exp == "multi_seed_compare":
        lines.append(_render_multi_seed_table(payload))
    elif exp == "high_load_compare":
        lines.append(_render_high_load_table(payload))
    elif exp == "llm_vs_baseline":
        lines.append(_render_single_table(payload))
    elif exp == "baseline_strategies":
        lines.append(_render_baseline_strategies_table(payload))
    else:
        lines.append("无法识别实验类型，原始文件可用于手工分析。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build markdown table report from experiment JSON files.")
    parser.add_argument(
        "--inputs",
        nargs="*",
        default=[],
        help="Input JSON files. If empty, auto-scan tests/output/exp_*.json",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="tests/output/experiment_report.md",
        help="Output markdown path",
    )
    args = parser.parse_args()

    if args.inputs:
        files = [Path(p) if Path(p).is_absolute() else ROOT / p for p in args.inputs]
    else:
        files = sorted(DEFAULT_OUTPUT_DIR.glob("exp_*.json"))

    reports = []
    for f in files:
        if not f.exists():
            continue
        payload = json.loads(f.read_text(encoding="utf-8"))
        reports.append(render_markdown(payload, f.name))

    out_path = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not reports:
        out_path.write_text("# 实验报告\n\n未找到可用实验 JSON。\n", encoding="utf-8")
    else:
        out_path.write_text("# 实验报告\n\n" + "\n".join(reports), encoding="utf-8")
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()

