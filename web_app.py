"""
网约车仿真 Web 演示（Streamlit）
包含：步进与自动跑满、乘客下单、司机状态、网格快照。

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
from pathlib import Path


# 必须在首次 import matplotlib / ridesim.visualizer 之前设置
os.environ.setdefault("RIDESIM_MPL_BACKEND", "Agg")

import streamlit as st

from ridesim import config
from ridesim.post_run_analysis import (
    generate_batch_analysis_markdown,
    generate_post_run_analysis_markdown,
)
from ridesim.run_persistence import (
    delete_ai_analysis,
    delete_saved_run,
    ensure_storage_dirs,
    list_saved_ai_files,
    list_saved_run_files,
    load_ai_meta_for,
    save_ai_analysis_markdown,
    save_run_snapshot,
)
from ridesim.simulation import Simulation
from ridesim.utils import driver as drv
from ridesim.visualizer import make_snapshot_figure

from matplotlib.pyplot import close as _plt_close_fig

# 左摘要 | 中地图 | 右留白：中间列几何中心在页面 50%，与上方 PLAY_CONTROL_CENTER_COLUMNS 之中列对齐
LAYOUT_SUMMARY_MAP_COLUMNS = [0.22, 0.56, 0.22]
PLAY_CONTROL_CENTER_COLUMNS = [1, 1, 1]
# 地图显示宽度：None = 撑满「地图」所在列（st.image use_container_width）；设为正整数则固定像素宽
MAP_IMAGE_DISPLAY_WIDTH_PX: int | None = 1000
AUTO_PLAY_DELAY_SEC = 0.12

# 侧栏可调网格范围（与仿真可行性一致；修改此处即可统一最小/最大格数）
GRID_WEB_MIN = 8
GRID_WEB_MAX = 60

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


def _render_map_snapshot(sim: Simulation) -> None:
    """将当前仿真状态渲染为 PNG，用 st.image 控制宽度（避免 st.pyplot 无法被外层 div 限制）。"""
    fig = make_snapshot_figure(sim.drivers, sim.orders, sim.current_step)
    buf = io.BytesIO()
    try:
        fig.savefig(
            buf,
            format="png",
            dpi=120,
            bbox_inches="tight",
            facecolor=fig.get_facecolor(),
        )
    finally:
        _plt_close_fig(fig)
    buf.seek(0)
    w = MAP_IMAGE_DISPLAY_WIDTH_PX
    if w is not None:
        st.image(buf, width=int(w))
    else:
        st.image(buf, use_container_width=True)


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


def _rerun_tabs_fragment_only() -> None:
    """主 Tab 区域局部刷新（演示/乘客/司机）；全页首次或旧版 Streamlit 时退回整页 rerun。"""
    try:
        st.rerun(scope="fragment")
    except TypeError:
        st.rerun()
    except Exception:
        st.rerun()


def _try_save_run_snapshot_if_complete(sim: Simulation) -> Path | None:
    """若已跑满当前轮，将结果写入 saved_runs/（每 _sim_serial 仅一次）。返回文件路径或 None。"""
    if sim.current_step < config.SIMULATION_STEPS:
        return None
    _snap_ser = st.session_state.get("_sim_serial", 0)
    if st.session_state.get("_run_snapshot_saved_serial") == _snap_ser:
        return None
    try:
        ensure_storage_dirs()
        path = save_run_snapshot(sim)
        st.session_state["_run_snapshot_saved_serial"] = _snap_ser
        return path
    except OSError:
        return None


@st.fragment
def _render_simulation_tabs_fragment() -> None:
    """演示+乘客+司机同一片段：步进/连播时三 Tab 一并刷新（乘客订单表每步更新）。"""
    sim = _ensure_sim()
    autoplay_advanced = False

    if st.session_state["_play_steps_remaining"] > 0:
        if sim.current_step < config.SIMULATION_STEPS:
            sim.run_step()
            st.session_state["_play_steps_remaining"] -= 1
            autoplay_advanced = True
        else:
            st.session_state["_play_steps_remaining"] = 0

    tab_demo, tab_passenger, tab_driver, tab_report = st.tabs(
        [
            "演示面板（执行 + 地图）",
            "乘客端 · 下单",
            "司机端 · 状态",
            "AI 仿真报告",
        ]
    )

    with tab_demo:
        _pad_l, _mid_ctrl, _pad_r = st.columns(PLAY_CONTROL_CENTER_COLUMNS, gap="small")
        with _pad_l:
            st.empty()
        with _mid_ctrl:
            n_jump = st.number_input(
                "连续执行步数",
                min_value=1,
                max_value=500,
                value=10,
                step=1,
                key="input_play_n_steps",
            )
            b_run, b_one, b_end = st.columns(3, gap="small")
            with b_run:
                if st.button("连续执行", key="btn_play_batch", type="secondary"):
                    if sim.current_step >= config.SIMULATION_STEPS:
                        st.warning("已达到最大步数。")
                    else:
                        st.session_state["_play_steps_remaining"] = int(n_jump)
                        st.session_state["_play_steps_requested"] = int(n_jump)
                        _rerun_tabs_fragment_only()
            with b_one:
                if st.button("执行一步", key="btn_one_step", type="secondary"):
                    if sim.current_step >= config.SIMULATION_STEPS:
                        st.warning("已达到最大步数。")
                    else:
                        sim.run_step()
            with b_end:
                _remain = max(0, config.SIMULATION_STEPS - sim.current_step)
                if st.button(
                    "自动执行至结束",
                    type="secondary",
                    key="btn_run_to_end",
                    disabled=_remain == 0,
                    help="与「连续执行」相同：按步刷新界面；步数=当前剩余步数（可大于 500）。",
                ):
                    if sim.current_step >= config.SIMULATION_STEPS:
                        st.warning("已达到最大步数。")
                    else:
                        st.session_state["_play_steps_remaining"] = int(_remain)
                        st.session_state["_play_steps_requested"] = int(_remain)
                        _rerun_tabs_fragment_only()
        with _pad_r:
            st.empty()

        summary_col, map_col, _map_pad = st.columns(LAYOUT_SUMMARY_MAP_COLUMNS, gap="small")
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
            st.caption("地图快照")
            _render_map_snapshot(sim)
        with _map_pad:
            st.empty()

        if st.session_state["_play_steps_remaining"] > 0:
            done = st.session_state["_play_steps_requested"] - st.session_state["_play_steps_remaining"]
            st.progress(
                done / max(1, st.session_state["_play_steps_requested"]),
                text=f"连续执行中：{done}/{st.session_state['_play_steps_requested']} 步",
            )

        _saved_run_path = _try_save_run_snapshot_if_complete(sim)
        if _saved_run_path is not None:
            st.success(
                f"仿真记录已写入 **`saved_runs/{_saved_run_path.name}`** ，「AI 仿真报告」第①节列表已同步。"
            )
            _toast = getattr(st, "toast", None)
            if callable(_toast):
                try:
                    _toast(f"已保存仿真记录：{_saved_run_path.name}", icon="📁")
                except Exception:
                    pass

    with tab_passenger:
        st.markdown(
            "在此模拟乘客发起订单（写入仿真订单池）。若开启「新订单强制等待一步」，下单当步不可被抢，下一步才可抢。"
        )
        _mx = max(0, config.GRID_SIZE - 1)
        _clamp_passenger_order_inputs(_mx)
        # 起点 / 终点分组：中间留白列拉开距离；组内两列使 number_input 更窄
        col_start_block, col_gap, col_end_block = st.columns([1.15, 0.45, 1.15], gap="large")
        with col_start_block:
            st.caption("起点")
            c_sx, c_sy = st.columns(2, gap="small")
            with c_sx:
                sx = st.number_input("X", min_value=0, max_value=_mx, step=1, key="web_passenger_sx")
            with c_sy:
                sy = st.number_input("Y", min_value=0, max_value=_mx, step=1, key="web_passenger_sy")
        with col_gap:
            st.markdown("")
        with col_end_block:
            st.caption("终点")
            c_ex, c_ey = st.columns(2, gap="small")
            with c_ex:
                ex = st.number_input("X", min_value=0, max_value=_mx, step=1, key="web_passenger_ex")
            with c_ey:
                ey = st.number_input("Y", min_value=0, max_value=_mx, step=1, key="web_passenger_ey")

        if st.button("提交订单"):
            try:
                order = sim.add_passenger_order(int(sx), int(sy), int(ex), int(ey))
                st.success(f"订单已创建：订单ID={order['id']}，预估车费={order['fare']}（曼哈顿距离×3）")
            except ValueError as e:
                st.error(str(e))

        st.subheader("订单列表")
        rows = []
        for o in sorted(sim.orders, key=lambda x: x["id"], reverse=True):
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
        st.markdown(
            "司机视角：策略、收入、里程、位置与当前订单；表格列头可点击排序，并对比大模型与规则组。"
        )
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
        st.dataframe(rows, width="stretch", height=980)

    with tab_report:
        _repo = Path(__file__).resolve().parent
        st.markdown(
            f"**存档目录（项目根下）**：`saved_runs/`（仿真 JSON）、`saved_ai_analyses/`（大模型 Markdown + 元数据）。"
            f"当前路径：`{_repo}`"
        )

        st.subheader("① 已保存的仿真结果")
        ensure_storage_dirs()
        run_files = list_saved_run_files()
        st.caption(
            f"`saved_runs/` 中共 **{len(run_files)}** 条记录；每次跑满「最大仿真步数」会自动追加一条。"
        )
        if run_files:
            _name_to_path = {p.name: p for p in run_files}
            _opts = [p.name for p in run_files]
            _chosen = st.multiselect(
                "勾选要交给大模型分析的仿真记录（下拉内逐项勾选，可多选；模型将结合项目说明与统计数据撰写报告）",
                options=_opts,
                default=[],
                key="multiselect_saved_runs_for_ai",
            )
            _b1, _b2 = st.columns([2, 1])
            with _b1:
                _do_batch = st.button(
                    "生成大模型综合分析（含项目基本情况说明）",
                    type="primary",
                    key="btn_batch_llm_analysis",
                )
            with _b2:
                st.caption("需配置 DEEPSEEK_API_KEY")

            if _do_batch:
                if not _chosen:
                    st.warning("请至少勾选一条仿真记录。")
                elif not os.getenv("DEEPSEEK_API_KEY"):
                    st.error("未检测到 DEEPSEEK_API_KEY，请在项目根目录 `.env` 配置后重启 Streamlit。")
                else:
                    _paths_sel = [_name_to_path[n] for n in _chosen]
                    with st.spinner("正在调用大模型（选中多条时可能需 1～2 分钟）…"):
                        _md_batch, _err_batch = generate_batch_analysis_markdown(_paths_sel)
                    if _err_batch:
                        st.error(_err_batch)
                    elif _md_batch:
                        save_ai_analysis_markdown(
                            _md_batch,
                            source_run_filenames=list(_chosen),
                            extra_meta={"analysis_type": "batch_from_saved_runs"},
                        )
                        st.success("分析已写入 `saved_ai_analyses/`，下方可查看或删除。")
                        _rerun_tabs_fragment_only()

            _del_pick = st.multiselect(
                "勾选要从磁盘删除的仿真存档（可多选，仅从磁盘删除 JSON）",
                options=_opts,
                default=[],
                key="multiselect_delete_saved_runs",
            )
            if st.button("删除所选仿真存档", key="btn_delete_run_file"):
                if not _del_pick:
                    st.warning("请至少勾选一条要删除的存档。")
                else:
                    for _n in _del_pick:
                        delete_saved_run(_name_to_path[_n])
                    _rerun_tabs_fragment_only()
        else:
            st.info("暂无存档。请将仿真跑满侧栏「最大仿真步数」，系统会自动保存 JSON。")

        st.divider()
        st.subheader("② 已保存的大模型分析报告")
        ai_files = list_saved_ai_files()
        if not ai_files:
            st.info("暂无 AI 报告。可在上方勾选记录生成，或使用下方「本轮快速解读」。")
        else:
            for _ap in ai_files:
                _meta = load_ai_meta_for(_ap)
                with st.expander(_ap.name, expanded=False):
                    if _meta:
                        st.json(_meta)
                    st.markdown(_ap.read_text(encoding="utf-8"))
            _ai_names = [_x.name for _x in ai_files]
            _pick_del_ai = st.multiselect(
                "勾选要删除的大模型报告（可多选）",
                options=_ai_names,
                default=[],
                key="multiselect_delete_ai_reports",
            )
            if st.button("删除所选报告文件", key="btn_delete_ai_report"):
                if not _pick_del_ai:
                    st.warning("请至少勾选一条要删除的报告。")
                else:
                    _map_ai = {p.name: p for p in ai_files}
                    for _n in _pick_del_ai:
                        delete_ai_analysis(_map_ai[_n])
                    _rerun_tabs_fragment_only()

        st.divider()
        st.subheader("③ 本轮仿真 · 快速 AI 解读（内存，可不勾选存档）")
        if sim.current_step < config.SIMULATION_STEPS:
            st.caption("请先跑满最大步数；跑满后会自动写入 `saved_runs/`，同时可用此处对「当前这一轮」立即生成解读。")
        else:
            if st.button("对当前已完成仿真立即生成 AI 解读并保存", key="btn_quick_ai_current"):
                if not os.getenv("DEEPSEEK_API_KEY"):
                    st.error("未检测到 DEEPSEEK_API_KEY。")
                else:
                    with st.spinner("正在调用大模型…"):
                        _qm, _qe = generate_post_run_analysis_markdown(sim)
                    if _qe:
                        st.error(_qe)
                    elif _qm:
                        save_ai_analysis_markdown(
                            _qm,
                            source_run_filenames=["<当前内存中的已完成仿真>"],
                            extra_meta={"analysis_type": "single_current_session"},
                        )
                        st.success("已保存至 `saved_ai_analyses/`。")
                        _rerun_tabs_fragment_only()

    if st.session_state["_play_steps_remaining"] > 0 and autoplay_advanced:
        time.sleep(AUTO_PLAY_DELAY_SEC)
        _rerun_tabs_fragment_only()


def _clamp_passenger_order_inputs(mx: int) -> None:
    """乘客下单坐标限制在 [0, mx]。网格改小后 Session 中旧坐标会大于 max，先钳制避免 StreamlitValueAboveMaxError。"""
    defaults = (
        ("web_passenger_sx", min(5, mx)),
        ("web_passenger_sy", min(5, mx)),
        ("web_passenger_ex", min(15, mx)),
        ("web_passenger_ey", min(15, mx)),
    )
    for key, default in defaults:
        if key not in st.session_state:
            st.session_state[key] = default
            continue
        try:
            v = int(st.session_state[key])
        except (TypeError, ValueError):
            v = default
        st.session_state[key] = max(0, min(mx, v))


def _order_slider_sync_to_num() -> None:
    st.session_state["g_order_p_num"] = round(float(st.session_state["g_order_p_slider"]), 2)


def _order_num_sync_to_slider() -> None:
    v = float(st.session_state["g_order_p_num"])
    v = max(0.01, min(1.2, v))
    st.session_state["g_order_p_num"] = round(v, 2)
    st.session_state["g_order_p_slider"] = float(st.session_state["g_order_p_num"])


def main():
    st.set_page_config(page_title="网约车调度仿真", layout="wide")
    st.markdown(
        """
        <style>
        """ + _STREAMLIT_STALE_GREY_FIX_CSS + """
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("网约车动态调度仿真 · 网页演示")

    with st.sidebar:
        st.header("全局参数（重置后生效）")
        _g0 = min(max(config.GRID_SIZE, GRID_WEB_MIN), GRID_WEB_MAX)
        g_grid = st.number_input(
            "网格大小",
            min_value=GRID_WEB_MIN,
            max_value=GRID_WEB_MAX,
            value=_g0,
            step=1,
            help=f"可调范围 {GRID_WEB_MIN}～{GRID_WEB_MAX}；应用后与 config.GRID_SIZE 同步。",
        )
        g_drivers = st.number_input("司机数量", min_value=2, max_value=50, value=config.NUM_DRIVERS, step=1)
        g_steps = st.number_input("最大仿真步数", min_value=20, max_value=2000, value=config.SIMULATION_STEPS, step=10)
        _op0 = float(getattr(config, "ORDER_PROBABILITY", 0.3))
        if "g_order_p_num" not in st.session_state:
            st.session_state["g_order_p_num"] = _op0
        if "g_order_p_slider" not in st.session_state:
            st.session_state["g_order_p_slider"] = _op0
        st.slider(
            "订单生成强度（每步期望订单数≈该值×时段倍数，与网格大小无关）",
            min_value=0.01,
            max_value=1.2,
            step=0.01,
            key="g_order_p_slider",
            on_change=_order_slider_sync_to_num,
            help="步长 0.01。数值偏小→订单少、司机易空闲；偏大→积压与等待变长。下方数字框可精确输入并与滑条联动。",
        )
        st.number_input(
            "订单生成强度（精确输入）",
            min_value=0.01,
            max_value=1.2,
            step=0.01,
            format="%.2f",
            key="g_order_p_num",
            on_change=_order_num_sync_to_slider,
            help="与上滑条同步；点「应用参数并重置仿真」时写入 config.ORDER_PROBABILITY。",
        )
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
            config.ORDER_PROBABILITY = float(st.session_state["g_order_p_num"])
            config.RANDOM_SEED = int(g_seed)
            config.USE_LLM_DRIVERS = bool(g_llm)
            config.NUM_LLM_DRIVERS = int(min(g_num_llm, g_drivers))
            config.NORMAL_STRATEGY = g_strategy
            if getattr(config, "AUTO_SCALE_ZONES", False):
                config.auto_scale_zone_params()
            st.session_state.pop("_sim", None)
            st.session_state.pop("_run_snapshot_saved_serial", None)
            _ensure_sim()
            st.rerun()

    _ensure_sim()
    st.session_state.setdefault("_play_steps_remaining", 0)
    st.session_state.setdefault("_play_steps_requested", 0)
    st.session_state.setdefault("_sim_serial", 0)

    _render_simulation_tabs_fragment()

if __name__ == "__main__":
    main()
