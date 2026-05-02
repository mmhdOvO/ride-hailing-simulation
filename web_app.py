"""
网约车仿真 Web 演示（Streamlit）
包含：仿真控制台、乘客下单、司机状态、网格快照。

运行（在项目根目录）:
  pip install streamlit
  streamlit run web_app.py

说明：Web 模式强制关闭独立 Tk 弹窗；网格图嵌入页面。
若开启 LLM，单步可能较慢，演示时可临时关闭 LLM。
"""
from __future__ import annotations

import contextlib
import io
import os
import time
from datetime import datetime

# 必须在首次 import matplotlib / ridesim.visualizer 之前设置
os.environ.setdefault("RIDESIM_MPL_BACKEND", "Agg")

import streamlit as st

from ridesim import config
from ridesim.post_run_analysis import generate_post_run_analysis_markdown
from ridesim.simulation import Simulation
from ridesim.utils import driver as drv
from ridesim.visualizer import make_snapshot_figure

import matplotlib.pyplot as plt

LAYOUT_MAIN_COLUMNS = [2.30, 0.62]
LAYOUT_SUMMARY_MAP_COLUMNS = [0.22, 0.78]
MAP_SHIFT_LEFT_PX = -128
MAP_SCALE_MAX_WIDTH = "60%"
MAP_INNER_COLUMNS = [0.03, 0.74, 0.23]
AUTO_PLAY_DELAY_SEC = 0.12
LOG_PANEL_HEIGHT = 930

# Streamlit 重跑时会把上一轮输出标成 stale 并降低透明度，看起来像整页变暗。
# 下列样式尽量抵消该效果（升级 Streamlit 后若失效需按新版 DOM 微调）。
_STREAMLIT_STALE_GREY_FIX_CSS = """
/* 抵消「上一轮组件」被半透明的灰色感 */
[stale-data="true"],
[data-stale="true"] {
    opacity: 1 !important;
    filter: none !important;
}
/* 部分构建使用此类名标记陈旧块 */
.stale-element {
    opacity: 1 !important;
}
"""


def _silence_init_simulation() -> Simulation:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return Simulation()


def _ensure_sim():
    if st.session_state.get("_sim") is None:
        backup_viz = config.VISUALIZE
        backup_dbg = config.DEBUG
        config.VISUALIZE = False
        config.DEBUG = False
        try:
            st.session_state["_sim"] = _silence_init_simulation()
        finally:
            config.VISUALIZE = backup_viz
            config.DEBUG = backup_dbg
        st.session_state["_sim_serial"] = st.session_state.get("_sim_serial", 0) + 1
    return st.session_state["_sim"]


def _reset_sim():
    st.session_state.pop("_sim", None)
    st.session_state.pop("_post_run_analysis_done_serial", None)
    st.session_state["_post_run_analysis_md"] = ""
    st.session_state.pop("_post_run_analysis_err", None)
    _ensure_sim()


def _append_console_log(message: str):
    logs = st.session_state.setdefault("_console_logs", [])
    ts = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{ts}] {message}")
    # 限制日志长度，避免页面越来越重
    if len(logs) > 120:
        del logs[: len(logs) - 120]


def _cn_order_status(status: str) -> str:
    return {
        "waiting": "等待中",
        "to_pickup": "前往接驾",
        "on_trip": "行程中",
        "completed": "已完成",
    }.get(status, status)


def _cn_driver_status(status: str) -> str:
    return {
        "idle": "空闲",
        "to_pickup": "前往接驾",
        "on_trip": "行程中",
    }.get(status, status)


def _cn_summary(data):
    """将摘要统计键名转为中文，便于演示。"""
    key_map = {
        "step": "当前步数",
        "drivers": "司机统计",
        "orders": "订单统计",
        "total": "总数",
        "idle": "空闲",
        "busy": "忙碌",
        "waiting": "等待中",
        "in_progress": "进行中",
        "completed": "已完成",
        "total_orders": "总订单数",
        "completed_orders": "已完成订单",
        "completion_rate": "完成率",
        "total_revenue": "总收入",
        "avg_waiting_time": "平均等待时长",
        "max_waiting_time": "最大等待时长",
        "revenue_gini": "收入基尼系数",
    }
    if isinstance(data, dict):
        return {key_map.get(k, k): _cn_summary(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_cn_summary(x) for x in data]
    return data


def _render_autoscroll_log(content: str, height: int, dom_id: str):
    """渲染日志框（原生组件，避免弃用 API）。"""
    st.text_area(
        label=dom_id,
        value=content or "",
        height=height,
        disabled=True,
        label_visibility="collapsed",
    )


def _print_summary_to_terminal(sim: Simulation):
    """将当前统计打印到启动 Streamlit 的终端（含排行榜与收入对比）。"""
    stats = sim.collect_statistics()
    print("\n" + "=" * 60)
    print("Web端触发：当前仿真统计报告")
    print("=" * 60)
    print(f"当前步数: {sim.current_step}/{config.SIMULATION_STEPS}")
    print(f"总订单数: {stats.get('total_orders', 0)}")
    print(f"完成订单数: {stats.get('completed_orders', 0)}")
    print(f"完成率: {stats.get('completion_rate', 0):.2f}%")
    print(f"总收入: {stats.get('total_revenue', 0)}")
    if "avg_waiting_time" in stats:
        print(f"平均等待时长: {stats['avg_waiting_time']:.2f}")
    if "max_waiting_time" in stats:
        print(f"最大等待时长: {stats['max_waiting_time']}")
    if "revenue_gini" in stats:
        print(f"收入基尼系数: {stats['revenue_gini']:.4f}")

    # 司机收入/效率对比
    llm_drivers = [d for d in sim.drivers if drv.is_llm(d)]
    rule_drivers = [d for d in sim.drivers if not drv.is_llm(d)]
    if llm_drivers and rule_drivers:
        llm_total = sum(drv.revenue(d) for d in llm_drivers)
        rule_total = sum(drv.revenue(d) for d in rule_drivers)
        llm_avg = llm_total / max(1, len(llm_drivers))
        rule_avg = rule_total / max(1, len(rule_drivers))
        llm_dist = sum(drv.distance(d) for d in llm_drivers)
        rule_dist = sum(drv.distance(d) for d in rule_drivers)
        llm_eff = llm_total / max(1, llm_dist)
        rule_eff = rule_total / max(1, rule_dist)
        print("\n--- 策略组对比（LLM vs 规则）---")
        print(f"LLM组: 人数={len(llm_drivers)} 总收入={llm_total} 人均收入={llm_avg:.2f} 收入/里程={llm_eff:.3f}")
        print(f"规则组: 人数={len(rule_drivers)} 总收入={rule_total} 人均收入={rule_avg:.2f} 收入/里程={rule_eff:.3f}")

    print("\n--- 司机收入排行榜 ---")
    sorted_drivers = sorted(sim.drivers, key=lambda d: drv.revenue(d), reverse=True)
    for i, d in enumerate(sorted_drivers, 1):
        d_type = "LLM" if drv.is_llm(d) else config.NORMAL_STRATEGY
        print(
            f"{i:2d}. 司机{drv.driver_id(d):2d} [{d_type:<10}] "
            f"收入={drv.revenue(d):4d} 里程={drv.distance(d):3d} 位置={drv.position(d)} 当前单={drv.current_order(d)}"
        )
    print("=" * 60)


def _rerun_tabs_fragment_only() -> None:
    """主 Tab 区域局部刷新（演示/乘客/司机）；全页首次或旧版 Streamlit 时退回整页 rerun。"""
    try:
        st.rerun(scope="fragment")
    except TypeError:
        st.rerun()
    except Exception:
        st.rerun()


@st.fragment
def _render_simulation_tabs_fragment() -> None:
    """演示+乘客+司机同一片段：步进/连播时三 Tab 一并刷新（乘客订单表每步更新）。"""
    sim = _ensure_sim()
    autoplay_advanced = False

    # 一轮仿真跑满后，自动调用大模型生成「结果解读」一次（与 _sim_serial 绑定，重置后重算）
    if sim.current_step >= config.SIMULATION_STEPS:
        _ser = st.session_state.get("_sim_serial", 0)
        if st.session_state.get("_post_run_analysis_done_serial") != _ser:
            if not os.getenv("DEEPSEEK_API_KEY"):
                st.session_state["_post_run_analysis_md"] = ""
                st.session_state["_post_run_analysis_err"] = (
                    "未检测到 DEEPSEEK_API_KEY。请在项目根目录 `.env` 中配置后，"
                    "在「AI 仿真报告」中点击「重新生成 AI 分析报告」；若刚添加密钥，需重启 Streamlit 以加载环境变量。"
                )
                st.session_state["_post_run_analysis_done_serial"] = _ser
            else:
                with st.spinner("正在生成 AI 仿真分析报告（调用大模型）…"):
                    _md, _err = generate_post_run_analysis_markdown(sim)
                st.session_state["_post_run_analysis_md"] = _md or ""
                st.session_state["_post_run_analysis_err"] = _err
                st.session_state["_post_run_analysis_done_serial"] = _ser

    if st.session_state["_play_steps_remaining"] > 0:
        if sim.current_step < config.SIMULATION_STEPS:
            sim.run_step()
            st.session_state["_play_steps_remaining"] -= 1
            autoplay_advanced = True
            done_steps = st.session_state["_play_steps_requested"] - st.session_state["_play_steps_remaining"]
            _append_console_log(f"连续执行中：已完成{done_steps}/{st.session_state['_play_steps_requested']}步，当前步数={sim.current_step}")
        else:
            st.session_state["_play_steps_remaining"] = 0

        if st.session_state["_play_steps_remaining"] <= 0:
            ran = sim.current_step - st.session_state["_play_start_step"]
            _append_console_log(
                f"连续执行完成：请求={st.session_state['_play_steps_requested']}步，实际={ran}步，当前步数={sim.current_step}"
            )
            if sim.current_step >= config.SIMULATION_STEPS and not st.session_state["_terminal_report_printed"]:
                _print_summary_to_terminal(sim)
                st.session_state["_terminal_report_printed"] = True
                _append_console_log("到达最大步数，已自动打印终端统计")

    tab_demo, tab_passenger, tab_driver, tab_report = st.tabs(
        [
            "演示面板（执行 + 地图）",
            "乘客端 · 下单",
            "司机端 · 状态",
            "AI 仿真报告",
        ]
    )

    with tab_demo:
        left, right = st.columns(LAYOUT_MAIN_COLUMNS, gap="small")
        with left:
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("执行一步", type="primary"):
                    if sim.current_step >= config.SIMULATION_STEPS:
                        st.warning("已达到最大步数。")
                        _append_console_log("执行一步失败：已达到最大步数")
                    else:
                        sim.run_step()
                        _append_console_log(f"执行一步完成：当前步数={sim.current_step}")
            with c2:
                n_jump = st.number_input("连续执行步数", min_value=1, max_value=500, value=10, step=1)
                if st.button("连续执行"):
                    if sim.current_step >= config.SIMULATION_STEPS:
                        st.warning("已达到最大步数。")
                        _append_console_log("连续执行失败：已达到最大步数")
                    else:
                        st.session_state["_play_steps_remaining"] = int(n_jump)
                        st.session_state["_play_steps_requested"] = int(n_jump)
                        st.session_state["_play_start_step"] = sim.current_step
                        _append_console_log(f"开始连续执行：计划={int(n_jump)}步")
                        # 连播计数在本按钮之后才写入；片段顶部已执行过，需立刻再跑一轮片段才会推进一步
                        _rerun_tabs_fragment_only()
            with c3:
                if st.button("仅重置仿真（保留侧边参数）"):
                    _reset_sim()
                    st.session_state["_terminal_report_printed"] = False
                    _append_console_log("仅重置仿真（侧边参数保留）")
                    st.rerun()
                if st.button("打印当前统计到终端"):
                    _print_summary_to_terminal(sim)
                    _append_console_log("已将当前统计打印到终端")
                    st.success("已打印到终端。")
    
            summary_col, map_col = st.columns(LAYOUT_SUMMARY_MAP_COLUMNS, gap="small")
            with summary_col:
                summary = sim.get_status_summary()
                st.subheader("当前摘要")
                st.json(_cn_summary(summary))
                stats = sim.collect_statistics()
                st.subheader("累计统计")
                keys = [
                    "total_orders",
                    "completed_orders",
                    "completion_rate",
                    "total_revenue",
                    "avg_waiting_time",
                    "max_waiting_time",
                    "revenue_gini",
                ]
                st.json(_cn_summary({k: stats[k] for k in keys if k in stats}))
            st.caption(f"当前步数 {sim.current_step} / {config.SIMULATION_STEPS}")
    
            with map_col:
                st.markdown("<div class='map-shift-left'>", unsafe_allow_html=True)
                st.caption("地图快照")
                _, map_mid, _ = st.columns(MAP_INNER_COLUMNS, gap="small")
                with map_mid:
                    st.markdown("<div class='map-scale-down'>", unsafe_allow_html=True)
                    fig = make_snapshot_figure(sim.drivers, sim.orders, sim.current_step)
                    st.pyplot(fig, width="stretch")
                    st.markdown("</div>", unsafe_allow_html=True)
                plt.close(fig)
                st.markdown("</div>", unsafe_allow_html=True)
    
            if st.session_state["_play_steps_remaining"] > 0:
                done = st.session_state["_play_steps_requested"] - st.session_state["_play_steps_remaining"]
                st.progress(
                    done / max(1, st.session_state["_play_steps_requested"]),
                    text=f"连续执行中：{done}/{st.session_state['_play_steps_requested']} 步",
                )
    
        with right:
            st.subheader("控制台信息流 · 仿真日志")
            logs = st.session_state.setdefault("_console_logs", [])
            if st.button("清空控制台日志"):
                st.session_state["_console_logs"] = []
            if logs:
                _render_autoscroll_log("\n".join(logs), LOG_PANEL_HEIGHT, "sim-log-box")
            else:
                st.info("暂无日志。执行仿真或提交订单后会显示记录。")

    with tab_passenger:
        st.markdown(
            "在此模拟乘客发起订单（写入仿真订单池）。若开启「新订单强制等待一步」，下单当步不可被抢，下一步才可抢。"
        )
        col_a, col_b = st.columns(2)
        with col_a:
            sx = st.number_input("起点 X", 0, config.GRID_SIZE - 1, 5)
            sy = st.number_input("起点 Y", 0, config.GRID_SIZE - 1, 5)
        with col_b:
            ex = st.number_input("终点 X", 0, config.GRID_SIZE - 1, 15)
            ey = st.number_input("终点 Y", 0, config.GRID_SIZE - 1, 15)

        if st.button("提交订单"):
            try:
                order = sim.add_passenger_order(int(sx), int(sy), int(ex), int(ey))
                st.success(f"订单已创建：订单ID={order['id']}，预估车费={order['fare']}（曼哈顿距离×3）")
                _append_console_log(
                    f"乘客下单：ID={order['id']} 起点=({order['start_x']},{order['start_y']}) "
                    f"终点=({order['end_x']},{order['end_y']}) 车费={order['fare']}"
                )
            except ValueError as e:
                st.error(str(e))

        st.subheader("订单列表（节选）")
        rows = []
        for o in sorted(sim.orders, key=lambda x: x["id"], reverse=True)[:30]:
            rows.append(
                {
                    "订单ID": o["id"],
                    "状态": _cn_order_status(o["status"]),
                    "起点": f"({o['start_x']},{o['start_y']})",
                    "终点": f"({o['end_x']},{o['end_y']})",
                    "车费": o.get("fare", "-"),
                    "等待步数": o.get("waiting_steps", 0),
                    "可抢单": o.get("ready_for_dispatch", True),
                }
            )
        if rows:
            st.dataframe(rows, width="stretch")
        else:
            st.info("暂无订单。")

    with tab_driver:
        st.markdown("司机视角：策略、收入、里程、位置与当前订单；可按收入排序，并对比大模型与规则组。")
        llm_d = [d for d in sim.drivers if drv.is_llm(d)]
        rule_d = [d for d in sim.drivers if not drv.is_llm(d)]
        if llm_d and rule_d:
            llm_rev = sum(drv.revenue(d) for d in llm_d)
            rule_rev = sum(drv.revenue(d) for d in rule_d)
            llm_dist = sum(drv.distance(d) for d in llm_d)
            rule_dist = sum(drv.distance(d) for d in rule_d)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("大模型组·总收入", f"{llm_rev}")
            c2.metric("规则组·总收入", f"{rule_rev}")
            c3.metric("大模型组·收入/里程", f"{(llm_rev / max(1, llm_dist)):.3f}")
            c4.metric("规则组·收入/里程", f"{(rule_rev / max(1, rule_dist)):.3f}")
            st.caption(
                f"大模型 {len(llm_d)} 人 人均 {llm_rev / max(1, len(llm_d)):.1f} 元 · "
                f"规则 {len(rule_d)} 人 人均 {rule_rev / max(1, len(rule_d)):.1f} 元"
            )

        sort_mode = st.selectbox(
            "列表排序",
            ("按司机ID", "按收入（高→低）", "按收入（低→高）"),
            index=0,
        )
        rows = []
        for d in sim.drivers:
            rows.append(
                {
                    "司机ID": drv.driver_id(d),
                    "策略(英文)": "llm" if drv.is_llm(d) else config.NORMAL_STRATEGY,
                    "收入": drv.revenue(d),
                    "里程": drv.distance(d),
                    "位置": str(drv.position(d)),
                    "当前订单": drv.current_order(d),
                }
            )
        if sort_mode == "按收入（高→低）":
            rows.sort(key=lambda r: r["收入"], reverse=True)
        elif sort_mode == "按收入（低→高）":
            rows.sort(key=lambda r: r["收入"])
        st.dataframe(rows, width="stretch", height=980)

    with tab_report:
        st.subheader("本轮仿真的大模型解读")
        st.caption("当「当前步数」达到侧栏「最大仿真步数」时，自动根据累计统计生成一次；更换参数或重置后会重新生成。")
        if sim.current_step < config.SIMULATION_STEPS:
            st.info("尚未跑满一次完整仿真。请使用「执行一步」或「连续执行」直到达到最大步数。")
        else:
            _err = st.session_state.get("_post_run_analysis_err")
            _md = st.session_state.get("_post_run_analysis_md", "")
            if _md:
                if _err:
                    st.caption(_err)
                st.markdown(_md)
            elif _err:
                st.warning(_err)
            else:
                st.caption("报告将在跑满步数后自动生成；若长时间无内容，请检查网络与 API 配置。")
            if st.button("重新生成 AI 分析报告", key="regen_post_run_analysis"):
                st.session_state.pop("_post_run_analysis_done_serial", None)
                st.session_state["_post_run_analysis_md"] = ""
                st.session_state.pop("_post_run_analysis_err", None)
                _rerun_tabs_fragment_only()

    if st.session_state["_play_steps_remaining"] > 0 and autoplay_advanced:
        time.sleep(AUTO_PLAY_DELAY_SEC)
        _rerun_tabs_fragment_only()


def main():
    st.set_page_config(page_title="网约车调度仿真", layout="wide")
    st.markdown(
        """
        <style>
        /* 演示布局微调参数，尽量集中在常量区便于后续调整 */
        .map-shift-left {
            margin-left: """ + str(MAP_SHIFT_LEFT_PX) + """px;
        }
        .map-scale-down {
            max-width: """ + MAP_SCALE_MAX_WIDTH + """;
        }
        """ + _STREAMLIT_STALE_GREY_FIX_CSS + """
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("网约车动态调度仿真 · 网页演示")

    with st.sidebar:
        st.header("全局参数（重置后生效）")
        g_grid = st.number_input("网格大小", min_value=8, max_value=60, value=config.GRID_SIZE, step=1)
        g_drivers = st.number_input("司机数量", min_value=2, max_value=50, value=config.NUM_DRIVERS, step=1)
        g_steps = st.number_input("最大仿真步数", min_value=20, max_value=2000, value=config.SIMULATION_STEPS, step=10)
        g_seed = st.number_input("随机种子", min_value=0, max_value=99999, value=config.RANDOM_SEED, step=1)
        g_llm = st.checkbox("启用大模型司机（较慢，演示可关）", value=config.USE_LLM_DRIVERS)
        g_num_llm = st.number_input("大模型司机数量", min_value=0, max_value=50, value=min(config.NUM_LLM_DRIVERS, config.NUM_DRIVERS), step=1)
        _strategies = ("nearest", "random", "round_robin")
        _si = _strategies.index(config.NORMAL_STRATEGY) if config.NORMAL_STRATEGY in _strategies else 0
        _strategy_labels = {
            "nearest": "最近优先",
            "random": "随机分配",
            "round_robin": "轮询分配",
        }
        _chosen_label = st.selectbox(
            "普通司机抢单策略",
            [_strategy_labels[s] for s in _strategies],
            index=_si,
        )
        g_strategy = {v: k for k, v in _strategy_labels.items()}[_chosen_label]

        if st.button("应用参数并重置仿真"):
            config.GRID_SIZE = int(g_grid)
            config.NUM_DRIVERS = int(g_drivers)
            config.SIMULATION_STEPS = int(g_steps)
            config.RANDOM_SEED = int(g_seed)
            config.USE_LLM_DRIVERS = bool(g_llm)
            config.NUM_LLM_DRIVERS = int(min(g_num_llm, g_drivers))
            config.NORMAL_STRATEGY = g_strategy
            if getattr(config, "AUTO_SCALE_ZONES", False):
                config.auto_scale_zone_params()
            st.session_state.pop("_sim", None)
            st.session_state.pop("_post_run_analysis_done_serial", None)
            st.session_state["_post_run_analysis_md"] = ""
            st.session_state.pop("_post_run_analysis_err", None)
            _ensure_sim()
            st.session_state["_terminal_report_printed"] = False
            _append_console_log(
                f"应用参数并重置：网格={config.GRID_SIZE}，司机数={config.NUM_DRIVERS}，"
                f"步数={config.SIMULATION_STEPS}，启用大模型={config.USE_LLM_DRIVERS}，策略={_strategy_labels.get(config.NORMAL_STRATEGY, config.NORMAL_STRATEGY)}"
            )
            st.rerun()

    _ensure_sim()
    st.session_state.setdefault("_play_steps_remaining", 0)
    st.session_state.setdefault("_play_steps_requested", 0)
    st.session_state.setdefault("_play_start_step", 0)
    st.session_state.setdefault("_terminal_report_printed", False)
    st.session_state.setdefault("_post_run_analysis_md", "")
    st.session_state.setdefault("_sim_serial", 0)

    _render_simulation_tabs_fragment()

if __name__ == "__main__":
    main()
