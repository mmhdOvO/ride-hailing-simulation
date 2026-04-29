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
from datetime import datetime

# 必须在首次 import matplotlib / ridesim.visualizer 之前设置
os.environ.setdefault("RIDESIM_MPL_BACKEND", "Agg")

import streamlit as st

from ridesim import config
from ridesim.simulation import Simulation
from ridesim.utils import driver as drv
from ridesim.visualizer import make_snapshot_figure

LAYOUT_MAIN_COLUMNS = [2.45, 0.45]
LAYOUT_SUMMARY_MAP_COLUMNS = [0.22, 0.78]
MAP_SHIFT_LEFT_PX = -128
MAP_SCALE_MAX_WIDTH = "74%"
MAP_INNER_COLUMNS = [0.03, 0.74, 0.23]


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
    return st.session_state["_sim"]


def _reset_sim():
    st.session_state.pop("_sim", None)
    _ensure_sim()


def _append_console_log(message: str):
    logs = st.session_state.setdefault("_console_logs", [])
    ts = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{ts}] {message}")
    # 限制日志长度，避免页面越来越重
    if len(logs) > 120:
        del logs[: len(logs) - 120]


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
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("网约车动态调度仿真 · Web 演示")

    with st.sidebar:
        st.header("全局参数（重置后生效）")
        g_grid = st.number_input("网格 GRID_SIZE", min_value=8, max_value=60, value=config.GRID_SIZE, step=1)
        g_drivers = st.number_input("司机数量", min_value=2, max_value=50, value=config.NUM_DRIVERS, step=1)
        g_steps = st.number_input("最大步数 SIMULATION_STEPS", min_value=20, max_value=2000, value=config.SIMULATION_STEPS, step=10)
        g_seed = st.number_input("随机种子", min_value=0, max_value=99999, value=config.RANDOM_SEED, step=1)
        g_llm = st.checkbox("启用 LLM 司机（较慢，演示可关）", value=config.USE_LLM_DRIVERS)
        g_num_llm = st.number_input("LLM 司机数量", min_value=0, max_value=50, value=min(config.NUM_LLM_DRIVERS, config.NUM_DRIVERS), step=1)
        _strategies = ("nearest", "random", "round_robin")
        _si = _strategies.index(config.NORMAL_STRATEGY) if config.NORMAL_STRATEGY in _strategies else 0
        g_strategy = st.selectbox("普通司机抢单策略", _strategies, index=_si)

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
            _ensure_sim()
            _append_console_log(
                f"应用参数并重置：grid={config.GRID_SIZE}, drivers={config.NUM_DRIVERS}, "
                f"steps={config.SIMULATION_STEPS}, llm={config.USE_LLM_DRIVERS}, strategy={config.NORMAL_STRATEGY}"
            )
            st.rerun()

    sim = _ensure_sim()

    tab_demo, tab_passenger, tab_driver = st.tabs(
        ["演示面板（执行 + 地图）", "乘客端 · 下单", "司机端 · 状态"]
    )

    with tab_demo:
        # 左侧主区域（控制+摘要+地图），右侧信息流
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
                        st.rerun()
            with c2:
                n_jump = st.number_input("连续执行步数", min_value=1, max_value=500, value=10, step=1)
                if st.button("连续执行"):
                    before = sim.current_step
                    for _ in range(int(n_jump)):
                        if sim.current_step >= config.SIMULATION_STEPS:
                            break
                        sim.run_step()
                    ran = sim.current_step - before
                    _append_console_log(f"连续执行完成：请求={int(n_jump)}步，实际={ran}步，当前步数={sim.current_step}")
                    st.rerun()
            with c3:
                if st.button("仅重置仿真（保留侧边参数）"):
                    _reset_sim()
                    _append_console_log("仅重置仿真（侧边参数保留）")
                    st.rerun()

            # 摘要放左，地图放右，填满原先空白区域
            summary_col, map_col = st.columns(LAYOUT_SUMMARY_MAP_COLUMNS, gap="small")
            with summary_col:
                summary = sim.get_status_summary()
                st.subheader("当前摘要")
                st.json(summary)
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
                st.json({k: stats[k] for k in keys if k in stats})
            st.caption(f"当前步数 {sim.current_step} / {config.SIMULATION_STEPS}")

            with map_col:
                st.markdown("<div class='map-shift-left'>", unsafe_allow_html=True)
                st.caption("地图快照")
                _, map_mid, _ = st.columns(MAP_INNER_COLUMNS, gap="small")
                with map_mid:
                    st.markdown("<div class='map-scale-down'>", unsafe_allow_html=True)
                    fig = make_snapshot_figure(sim.drivers, sim.orders, sim.current_step)
                    st.pyplot(fig, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                import matplotlib.pyplot as plt

                plt.close(fig)
                st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.subheader("控制台信息流")
            logs = st.session_state.setdefault("_console_logs", [])
            if st.button("清空控制台日志"):
                st.session_state["_console_logs"] = []
                st.rerun()
            if logs:
                st.code("\n".join(reversed(logs)), language="text")
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
                st.success(f"订单已创建：ID={order['id']}，预估车费={order['fare']}（曼哈顿×3）")
                _append_console_log(
                    f"乘客下单：ID={order['id']} 起点=({order['start_x']},{order['start_y']}) "
                    f"终点=({order['end_x']},{order['end_y']}) 车费={order['fare']}"
                )
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        st.subheader("订单列表（节选）")
        rows = []
        for o in sorted(sim.orders, key=lambda x: x["id"], reverse=True)[:30]:
            rows.append(
                {
                    "ID": o["id"],
                    "状态": o["status"],
                    "起点": f"({o['start_x']},{o['start_y']})",
                    "终点": f"({o['end_x']},{o['end_y']})",
                    "车费": o.get("fare", "-"),
                    "等待步数": o.get("waiting_steps", 0),
                    "可抢单": o.get("ready_for_dispatch", True),
                }
            )
        if rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info("暂无订单。")

    with tab_driver:
        st.markdown("司机视角：查看编号、类型、状态、收入与位置。")
        rows = []
        for d in sim.drivers:
            rows.append(
                {
                    "司机ID": drv.driver_id(d),
                    "类型": "LLM" if drv.is_llm(d) else "规则",
                    "状态": drv.status(d),
                    "收入": drv.revenue(d),
                    "里程": drv.distance(d),
                    "位置": str(drv.position(d)),
                    "当前订单": drv.current_order(d),
                }
            )
        st.dataframe(rows, use_container_width=True)

if __name__ == "__main__":
    main()
