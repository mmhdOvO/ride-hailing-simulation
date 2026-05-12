"""
第6章：多随机种子批量仿真实验。

用法（在仓库根目录）:
  python scripts/ch6_batch_experiments.py

输出:
  - experiments/ch6_results.json   原始逐次指标
  - docs/thesis_ch6_data.md        汇总表与可粘贴正文片段

说明:
  - 纯规则实验默认 10 个种子；含 LLM 的实验默认 5 个种子（可用环境变量覆盖）。
  - 需配置 .env 中的 DEEPSEEK_API_KEY；否则会跳过所有 LLM 相关实验。
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass, asdict
from io import StringIO
from pathlib import Path

# 仓库根目录
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)


def _use_agg_backend() -> None:
    import matplotlib

    matplotlib.use("Agg")


def _mean_std(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return float("nan"), float("nan")
    m = statistics.mean(xs)
    if len(xs) < 2:
        return m, 0.0
    return m, statistics.stdev(xs)


def _fmt_mean_std(m: float, s: float, nd: int = 1) -> str:
    if s <= 1e-9:
        return f"{m:.{nd}f}"
    return f"{m:.{nd}f}±{s:.{nd}f}"


@dataclass
class RunRecord:
    scenario: str
    seed: int
    stats: dict
    wall_seconds: float
    llm_group: dict | None = None
    rule_group: dict | None = None


def _group_llm_rule(sim) -> tuple[dict | None, dict | None]:
    from ridesim.utils import driver as drv

    llm_rev = llm_dist = 0.0
    rule_rev = rule_dist = 0.0
    ln = rn = 0
    for d in sim.drivers:
        if drv.is_llm(d):
            llm_rev += drv.revenue(d)
            llm_dist += drv.distance(d)
            ln += 1
        else:
            rule_rev += drv.revenue(d)
            rule_dist += drv.distance(d)
            rn += 1
    if ln == 0 or rn == 0:
        return None, None
    return (
        {
            "n": ln,
            "total_revenue": llm_rev,
            "total_distance": llm_dist,
            "rev_per_driver": llm_rev / ln,
            "rev_per_cell": llm_rev / max(1, llm_dist),
        },
        {
            "n": rn,
            "total_revenue": rule_rev,
            "total_distance": rule_dist,
            "rev_per_driver": rule_rev / rn,
            "rev_per_cell": rule_rev / max(1, rule_dist),
        },
    )


def run_once(
    *,
    seed: int,
    use_llm: bool,
    num_llm: int,
    num_drivers: int,
    normal_strategy: str,
    use_road_network: bool,
    ch6_ablation_mode: str,
) -> tuple[dict, float, dict | None, dict | None]:
    import ridesim.config as cfg
    from ridesim.simulation import Simulation

    cfg.RANDOM_SEED = int(seed)
    cfg.VISUALIZE = False
    cfg.DEBUG = False
    cfg.USE_LLM_DRIVERS = bool(use_llm)
    cfg.NUM_LLM_DRIVERS = int(num_llm) if use_llm else 0
    cfg.NUM_DRIVERS = int(num_drivers)
    cfg.NORMAL_STRATEGY = normal_strategy
    cfg.USE_ROAD_NETWORK = bool(use_road_network)
    cfg.CH6_ABLATION_MODE = ch6_ablation_mode or "none"

    buf = StringIO()
    t0 = time.perf_counter()
    with redirect_stdout(buf):
        sim = Simulation()
        while sim.current_step < cfg.SIMULATION_STEPS:
            sim.run_step()
        stats = sim.collect_statistics()
        lg, rg = _group_llm_rule(sim)
    elapsed = time.perf_counter() - t0
    return stats, elapsed, lg, rg


def main() -> int:
    _use_agg_backend()

    rule_seeds = [int(x) for x in os.getenv("CH6_RULE_SEEDS", "42,47,53,61,67,71,73,79,83,89").split(",")]
    # 默认 5 个种子；可通过环境变量 CH6_LLM_SEEDS 覆盖（逗号分隔）
    llm_seeds = [int(x) for x in os.getenv("CH6_LLM_SEEDS", "42,56,63,71,89").split(",") if x.strip()]

    has_key = bool(os.getenv("DEEPSEEK_API_KEY"))
    if not has_key:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        has_key = bool(os.getenv("DEEPSEEK_API_KEY"))

    records: list[RunRecord] = []

    # ----- 纯规则：三种策略 × 多种子 -----
    for strat in ("nearest", "random", "round_robin"):
        name = f"rule_{strat}"
        for sd in rule_seeds:
            st, wall, _, _ = run_once(
                seed=sd,
                use_llm=False,
                num_llm=0,
                num_drivers=20,
                normal_strategy=strat,
                use_road_network=True,
                ch6_ablation_mode="none",
            )
            records.append(RunRecord(name, sd, st, wall, None, None))

    # ----- LLM 混合 + 纯规则 nearest 对照 -----
    if has_key:
        for sd in llm_seeds:
            st, wall, lg, rg = run_once(
                seed=sd,
                use_llm=True,
                num_llm=10,
                num_drivers=20,
                normal_strategy="nearest",
                use_road_network=True,
                ch6_ablation_mode="none",
            )
            records.append(RunRecord("llm_mixed", sd, st, wall, lg, rg))

        for sd in llm_seeds:
            st, wall, _, _ = run_once(
                seed=sd,
                use_llm=False,
                num_llm=0,
                num_drivers=20,
                normal_strategy="nearest",
                use_road_network=True,
                ch6_ablation_mode="none",
            )
            records.append(RunRecord("pure_rule_nearest", sd, st, wall, None, None))

        # ----- 消融（混合车队） -----
        ablations = [
            ("ablation_no_road", False, "none"),
            ("ablation_no_competition", True, "no_competition"),
            ("ablation_no_zone", True, "no_zone"),
            ("ablation_no_followup", True, "no_followup"),
        ]
        for scen, road, abmode in ablations:
            for sd in llm_seeds:
                st, wall, lg, rg = run_once(
                    seed=sd,
                    use_llm=True,
                    num_llm=10,
                    num_drivers=20,
                    normal_strategy="nearest",
                    use_road_network=road,
                    ch6_ablation_mode=abmode,
                )
                records.append(RunRecord(scen, sd, st, wall, lg, rg))
    else:
        print("未检测到 DEEPSEEK_API_KEY，已跳过 LLM 与消融实验。", file=sys.stderr)

    out_dir = ROOT / "experiments"
    out_dir.mkdir(exist_ok=True)
    json_path = out_dir / "ch6_results.json"
    serializable = [asdict(r) for r in records]
    json_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"已写入 {json_path}")

    # ----- 汇总写 Markdown -----
    def collect(scenario: str, key: str) -> list[float]:
        return [float(r.stats[key]) for r in records if r.scenario == scenario and key in r.stats]

    def collect_nested(scenario: str, group: str, key: str) -> list[float]:
        out = []
        for r in records:
            if r.scenario != scenario:
                continue
            g = r.llm_group if group == "llm" else r.rule_group
            if not g or key not in g:
                continue
            out.append(float(g[key]))
        return out

    lines: list[str] = []
    lines.append("# 第6章 实验数据（多次独立重复）\n")
    lines.append(
        f"生成：`python scripts/ch6_batch_experiments.py`；规则组种子 {len(rule_seeds)} 个；"
        f"LLM 相关种子 {len(llm_seeds)} 个。\n"
    )

    lines.append("## 表6.3 无LLM：三种规则策略（均值±标准差）\n")
    lines.append("| 策略 | 总订单 | 完成率(%) | 总收入(元) | 总里程(格) | 收入/里程 |")
    lines.append("|------|--------|-----------|------------|------------|-----------|")
    for strat in ("nearest", "random", "round_robin"):
        sc = f"rule_{strat}"
        to = collect(sc, "total_orders")
        cr = collect(sc, "completion_rate")
        tr = collect(sc, "total_revenue")
        td = collect(sc, "total_distance")
        rpm = [tr[i] / max(1, td[i]) for i in range(len(tr))]
        lines.append(
            f"| {strat} | {_fmt_mean_std(statistics.mean(to), statistics.stdev(to) if len(to) > 1 else 0, 1)} "
            f"| {_fmt_mean_std(statistics.mean(cr), statistics.stdev(cr) if len(cr) > 1 else 0, 1)} "
            f"| {_fmt_mean_std(statistics.mean(tr), statistics.stdev(tr) if len(tr) > 1 else 0, 0)} "
            f"| {_fmt_mean_std(statistics.mean(td), statistics.stdev(td) if len(td) > 1 else 0, 0)} "
            f"| {_fmt_mean_std(statistics.mean(rpm), statistics.stdev(rpm) if len(rpm) > 1 else 0, 3)} |"
        )
    lines.append("")

    if has_key:
        lines.append("## 表6.4 LLM混合车队 vs 纯规则 nearest（均值±标准差）\n")
        lines.append("| 车队配置 | 总订单 | 完成率(%) | 总收入(元) | 总里程(格) | 收入/里程 | 墙钟耗时(s) |")
        lines.append("|----------|--------|-----------|------------|------------|-----------|-------------|")
        for label, sc in (
            ("LLM混合(10+10)", "llm_mixed"),
            ("纯规则(20)+nearest", "pure_rule_nearest"),
        ):
            to = collect(sc, "total_orders")
            cr = collect(sc, "completion_rate")
            tr = collect(sc, "total_revenue")
            td = collect(sc, "total_distance")
            wall = [r.wall_seconds for r in records if r.scenario == sc]
            rpm = [tr[i] / max(1, td[i]) for i in range(len(tr))]
            lines.append(
                f"| {label} | {_fmt_mean_std(statistics.mean(to), statistics.stdev(to) if len(to) > 1 else 0, 1)} "
                f"| {_fmt_mean_std(statistics.mean(cr), statistics.stdev(cr) if len(cr) > 1 else 0, 1)} "
                f"| {_fmt_mean_std(statistics.mean(tr), statistics.stdev(tr) if len(tr) > 1 else 0, 0)} "
                f"| {_fmt_mean_std(statistics.mean(td), statistics.stdev(td) if len(td) > 1 else 0, 0)} "
                f"| {_fmt_mean_std(statistics.mean(rpm), statistics.stdev(rpm) if len(rpm) > 1 else 0, 3)} "
                f"| {_fmt_mean_std(statistics.mean(wall), statistics.stdev(wall) if len(wall) > 1 else 0, 1)} |"
            )
        lines.append("")

        lines.append("## 表6.5 混合车队内 LLM组 vs 规则组（各次实验均值±标准差）\n")
        lines.append("| 组别 | 人均收入(元) | 收入/里程 |")
        lines.append("|------|-------------|-----------|")
        for gname, gkey in (("LLM组", "llm"), ("规则组", "rule")):
            rpd = collect_nested("llm_mixed", gkey, "rev_per_driver")
            rpc = collect_nested("llm_mixed", gkey, "rev_per_cell")
            lines.append(
                f"| {gname} | {_fmt_mean_std(statistics.mean(rpd), statistics.stdev(rpd) if len(rpd) > 1 else 0, 1)} "
                f"| {_fmt_mean_std(statistics.mean(rpc), statistics.stdev(rpc) if len(rpc) > 1 else 0, 3)} |"
            )
        lines.append("")

        lines.append("## 表6.8 各组收入/里程效率及 LLM 相对规则组优势（同批种子均值）\n")
        lines.append("| 实验 | LLM组 收入/里程 | 规则组 收入/里程 | LLM 效率优势 |")
        lines.append("|------|----------------|-----------------|--------------|")
        scen_eff = [
            ("llm_mixed（完整系统）", "llm_mixed"),
            ("无道路网络", "ablation_no_road"),
            ("无竞争惩罚", "ablation_no_competition"),
            ("无区域前瞻分", "ablation_no_zone"),
            ("无后续潜力分", "ablation_no_followup"),
        ]
        for label, sc in scen_eff:
            lr = collect_nested(sc, "llm", "rev_per_cell")
            rr = collect_nested(sc, "rule", "rev_per_cell")
            if not lr or not rr:
                continue
            m_l, m_r = statistics.mean(lr), statistics.mean(rr)
            adv = (m_l - m_r) / m_r * 100 if m_r else float("nan")
            lines.append(f"| {label} | {m_l:.3f} | {m_r:.3f} | {adv:+.1f}% |")
        lines.append("")

        lines.append("## 表6.6 订单等待步数（各场景平均等待为多次实验均值；最长/最短列为各次实验中的极值）\n")
        lines.append("| 实验 | 平均等待 | 最长等待 | 最短等待 |")
        lines.append("|------|----------|----------|----------|")
        scenarios_wait = [
            ("最近优先（纯规则）", "rule_nearest"),
            ("随机（纯规则）", "rule_random"),
            ("轮询（纯规则）", "rule_round_robin"),
            ("LLM 混合车队", "llm_mixed"),
            ("消融：无道路网络", "ablation_no_road"),
            ("消融：无竞争惩罚", "ablation_no_competition"),
            ("消融：无区域前瞻分", "ablation_no_zone"),
            ("消融：无后续潜力分", "ablation_no_followup"),
        ]
        for label, sc in scenarios_wait:
            avgs = [r.stats.get("avg_waiting_time") for r in records if r.scenario == sc and "avg_waiting_time" in r.stats]
            maxs = [r.stats.get("max_waiting_time") for r in records if r.scenario == sc and "max_waiting_time" in r.stats]
            mins = [r.stats.get("min_waiting_time") for r in records if r.scenario == sc and "min_waiting_time" in r.stats]
            if not avgs:
                continue
            lines.append(
                f"| {label} | {statistics.mean(avgs):.2f} | {max(maxs) if maxs else '-'} | {min(mins) if mins else '-'} |"
            )
        lines.append("")

        lines.append("## 表6.7 公平性指标（均值±标准差）\n")
        lines.append("| 实验 | Gini | CV | 最低收入 | 最高收入 | 极差(均值) |")
        lines.append("|------|------|-----|----------|----------|------------|")
        scenarios_fair = [
            ("最近优先（纯规则）", "rule_nearest"),
            ("随机（纯规则）", "rule_random"),
            ("轮询（纯规则）", "rule_round_robin"),
            ("LLM 混合车队", "llm_mixed"),
            ("消融：无道路网络", "ablation_no_road"),
            ("消融：无竞争惩罚", "ablation_no_competition"),
            ("消融：无区域前瞻分", "ablation_no_zone"),
            ("消融：无后续潜力分", "ablation_no_followup"),
        ]
        for label, sc in scenarios_fair:
            g = collect(sc, "revenue_gini")
            cv = collect(sc, "revenue_cv")
            mi = collect(sc, "min_revenue")
            ma = collect(sc, "max_revenue")
            if not g:
                continue
            # 极差 = max - min（单次仿真内）
            spans = [
                r.stats["max_revenue"] - r.stats["min_revenue"]
                for r in records
                if r.scenario == sc and "min_revenue" in r.stats
            ]
            lines.append(
                f"| {label} | {_fmt_mean_std(statistics.mean(g), statistics.stdev(g) if len(g) > 1 else 0, 4)} "
                f"| {_fmt_mean_std(statistics.mean(cv), statistics.stdev(cv) if len(cv) > 1 else 0, 4)} "
                f"| {_fmt_mean_std(statistics.mean(mi), statistics.stdev(mi) if len(mi) > 1 else 0, 0)} "
                f"| {_fmt_mean_std(statistics.mean(ma), statistics.stdev(ma) if len(ma) > 1 else 0, 0)} "
                f"| {_fmt_mean_std(statistics.mean(spans), statistics.stdev(spans) if len(spans) > 1 else 0, 0)} |"
            )
        lines.append("")

        lines.append("## 表6.9～6.11 消融：相对「llm_mixed」同批种子的均值\n")
        base_cr = statistics.mean(collect("llm_mixed", "completion_rate"))
        base_rev = statistics.mean(collect("llm_mixed", "total_revenue"))
        base_gini = statistics.mean(collect("llm_mixed", "revenue_gini"))
        base_llm_rpc = statistics.mean(collect_nested("llm_mixed", "llm", "rev_per_cell"))
        base_rule_rpc = statistics.mean(collect_nested("llm_mixed", "rule", "rev_per_cell"))

        def ab_row(title: str, scen: str) -> str:
            cr = statistics.mean(collect(scen, "completion_rate"))
            rev = statistics.mean(collect(scen, "total_revenue"))
            gin = statistics.mean(collect(scen, "revenue_gini"))
            lr = statistics.mean(collect_nested(scen, "llm", "rev_per_cell"))
            rr = statistics.mean(collect_nested(scen, "rule", "rev_per_cell"))
            return (
                f"| {title} | 完成率 {cr:.1f}% (Δ{cr - base_cr:+.1f}pp) | 总收入 {rev:.0f} (Δ{rev - base_rev:+.0f}) | "
                f"Gini {gin:.4f} (Δ{gin - base_gini:+.4f}) | LLM收入/里程 {lr:.3f} (Δ{lr - base_llm_rpc:+.3f}) | "
                f"规则收入/里程 {rr:.3f} (Δ{rr - base_rule_rpc:+.3f}) |"
            )

        lines.append("| 消融 | 相对完整系统（同批种子均值对比） |")
        lines.append("|------|--------------------------------------|")
        lines.append(ab_row("无道路网络", "ablation_no_road"))
        lines.append(ab_row("无竞争惩罚", "ablation_no_competition"))
        lines.append(ab_row("无区域前瞻分", "ablation_no_zone"))
        lines.append(ab_row("无后续潜力分", "ablation_no_followup"))
        lines.append("")

        lines.append("## 6.x 正文可引用句（示例）\n")
        lines.append(
            f"在默认参数下，对三种纯规则策略各独立重复 {len(rule_seeds)} 次（不同随机种子），"
            "完成率、总收入等指标在表中报告为均值±标准差；同一配置下文简称「多次实验均值」。"
        )
        lines.append(
            f"含 LLM 的混合车队、纯规则对照及各项消融实验均在 {len(llm_seeds)} 个种子上重复，"
            "以观察随机波动；墙钟时间为本机一次完整仿真耗时，含 API 调用。"
        )
    else:
        lines.append("_（未运行 LLM 实验，配置密钥后可重新执行脚本生成表6.4～6.11。）_\n")

    md_path = ROOT / "docs" / "thesis_ch6_data.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已写入 {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
