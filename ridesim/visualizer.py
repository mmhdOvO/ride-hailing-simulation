"""
visualizer.py
仿真过程可视化
使用Matplotlib绘制动态网格图
"""
import os
import matplotlib

# Web/Streamlit 等场景可设环境变量 RIDESIM_MPL_BACKEND=Agg 再 import 本包
matplotlib.use(os.environ.get("RIDESIM_MPL_BACKEND", "TkAgg"))

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

from . import config
from .utils import driver as drv, get_road_mask

DARK_BG = "#0b1220"
DARK_AX_BG = "#111a2e"
DARK_GRID = "#7e94bf"
DARK_TEXT = "#ffffff"


def _legend_font():
    """图例字体：优先微软雅黑文件，缺失则用 sans-serif。"""
    path = "C:/Windows/Fonts/msyh.ttc"
    try:
        return FontProperties(fname=path, size=8)
    except OSError:
        return FontProperties(family='sans-serif', size=8)


def setup_plot_axes(ax):
    """设置坐标轴、区域背景与图例（供动态窗口与静态快照共用）。"""
    ax.clear()
    if ax.figure is not None:
        ax.figure.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_AX_BG)
    ax.set_xlim(-0.5, config.GRID_SIZE - 0.5)
    ax.set_ylim(-0.5, config.GRID_SIZE - 0.5)
    ax.set_aspect('equal')
    ax.set_xticks(range(config.GRID_SIZE))
    ax.set_yticks(range(config.GRID_SIZE))
    ax.grid(True, linestyle=':', color=DARK_GRID, alpha=0.95, linewidth=0.9)
    ax.set_xlabel('X坐标', color=DARK_TEXT)
    ax.set_ylabel('Y坐标', color=DARK_TEXT)
    ax.tick_params(colors=DARK_TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color("#6f84ad")
    ax.invert_yaxis()

    # 伪真实道路底图：非道路区域加深，道路保持通透
    if getattr(config, "USE_ROAD_NETWORK", False):
        road_mask = get_road_mask()
        for y in range(config.GRID_SIZE):
            for x in range(config.GRID_SIZE):
                if not road_mask[y][x]:
                    ax.add_patch(
                        patches.Rectangle(
                            (x - 0.5, y - 0.5),
                            1.0,
                            1.0,
                            facecolor="#060b16",
                            edgecolor="none",
                            alpha=0.62,
                            zorder=0,
                        )
                    )

    if config.USE_ZONES:
        residential = patches.Circle(
            (config.RESIDENTIAL_CENTER_X, config.RESIDENTIAL_CENTER_Y),
            config.RESIDENTIAL_RADIUS,
            linewidth=1.5,
            edgecolor='#5ea3ff',
            facecolor='#4b91ff',
            alpha=0.18,
            linestyle='--',
            zorder=1,
        )
        ax.add_patch(residential)
        ax.text(
            config.RESIDENTIAL_CENTER_X,
            config.RESIDENTIAL_CENTER_Y,
            "居民区",
            ha='center',
            va='center',
            fontsize=9,
            color='#9fc8ff',
            fontweight='bold',
            zorder=2,
        )

        work_area = patches.Circle(
            (config.WORK_AREA_CENTER_X, config.WORK_AREA_CENTER_Y),
            config.WORK_AREA_RADIUS,
            linewidth=1.5,
            edgecolor='#d6a15e',
            facecolor='#f1b96c',
            alpha=0.18,
            linestyle='--',
            zorder=1,
        )
        ax.add_patch(work_area)
        ax.text(
            config.WORK_AREA_CENTER_X,
            config.WORK_AREA_CENTER_Y,
            "工作区",
            ha='center',
            va='center',
            fontsize=9,
            color='#ffd59f',
            fontweight='bold',
            zorder=2,
        )

    font = _legend_font()
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#ff6b81', markersize=10, label='订单-等待中'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='none', markeredgecolor='#ffd166', markeredgewidth=2, markersize=10, label='订单-已接(赶往)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#58b3ff', markersize=10, label='司机-空闲'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#ffd166', markersize=10, label='司机-去接'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='#5cf2a5', markersize=10, label='司机-送客'),
        patches.Patch(facecolor='#4b91ff', edgecolor='#5ea3ff', alpha=0.30, label='居民区范围'),
        patches.Patch(facecolor='#f1b96c', edgecolor='#d6a15e', alpha=0.30, label='工作区范围'),
    ]
    if config.DISTINGUISH_LLM_IN_VIZ:
        legend_elements.insert(
            5,
            Line2D([0], [0], marker='o', color='w', markerfacecolor='#ba68ff', markersize=10, label='LLM司机'),
        )
    leg = ax.legend(handles=legend_elements, loc='upper right')
    leg.get_frame().set_facecolor("#0f1a30")
    leg.get_frame().set_edgecolor("#9ab4e8")
    leg.get_frame().set_alpha(0.97)
    for text in leg.get_texts():
        text.set_fontproperties(font)
        text.set_color(DARK_TEXT)


def _draw_frame(ax, drivers, orders, current_step):
    """在已 setup 的坐标轴上绘制订单与司机。"""
    ratio = current_step / max(1, config.SIMULATION_STEPS)
    if config.USE_TIME_PERIODS and config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END:
        period_label = "早高峰"
        period_color = "#ff6b81"
    elif config.USE_TIME_PERIODS and config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END:
        period_label = "晚高峰"
        period_color = "#ffb347"
    else:
        period_label = "平峰"
        period_color = "#c8d7ff"

    ax.set_title(f'网约车仿真 - 时间步: {current_step} | 时段: {period_label}', color=DARK_TEXT)
    ax.text(
        0.02,
        0.98,
        f"当前时段: {period_label}",
        transform=ax.transAxes,
        ha='left',
        va='top',
        fontsize=10,
        color=period_color,
        fontweight='bold',
        bbox=dict(boxstyle='round,pad=0.25', facecolor='#1b2844', edgecolor=period_color, alpha=0.9),
        zorder=30,
    )

    for order in orders:
        if order['status'] == 'waiting':
            start_circle = patches.Circle((order['start_x'], order['start_y']),
                                          0.25, color='#ff6b81', alpha=1.0, zorder=8)
            ax.add_patch(start_circle)
            ax.text(order['start_x'], order['start_y'] - 0.4,
                    f"O{order['id']}", ha='center', va='center',
                    fontsize=8, color='#fff3f5', fontweight='bold')

        elif order['status'] == 'to_pickup':
            start_circle = patches.Circle((order['start_x'], order['start_y']),
                                          0.28, linewidth=2,
                                          edgecolor='#ffd166', facecolor='none',
                                          alpha=1.0, zorder=7)
            ax.add_patch(start_circle)
            ax.text(order['start_x'], order['start_y'] - 0.4,
                    f"O{order['id']}", ha='center', va='center',
                    fontsize=8, color='#fff1d6', fontweight='bold')
            ax.text(order['start_x'], order['start_y'] + 0.4,
                    f"(赶往)", ha='center', va='center',
                    fontsize=6, color='#fff1d6')

        if order['status'] in ['waiting', 'to_pickup']:
            end_rect = patches.Rectangle((order['end_x'] - 0.35, order['end_y'] - 0.35),
                                         0.7, 0.7, linewidth=1.5,
                                         edgecolor='#ff5f6d', facecolor='none',
                                         linestyle='--', alpha=0.4)
            ax.add_patch(end_rect)

    for driver in drivers:
        status = drv.status(driver)
        x, y = drv.x(driver), drv.y(driver)
        driver_id = drv.driver_id(driver)
        is_llm = drv.is_llm(driver)

        color_map = {'idle': '#58b3ff', 'to_pickup': '#ffd166', 'on_trip': '#5cf2a5'}
        color = color_map.get(status, '#b8c4df')
        if is_llm and config.DISTINGUISH_LLM_IN_VIZ:
            color = '#ba68ff'

        driver_circle = patches.Circle((x, y), 0.35, color=color, alpha=0.8, zorder=10)
        ax.add_patch(driver_circle)

        if config.PLOT_DRIVER_NUM:
            highlight_llm = is_llm and config.DISTINGUISH_LLM_IN_VIZ
            text_color = '#ffe27a' if highlight_llm else '#ffffff'
            fontweight = 'bold' if highlight_llm else 'normal'
            ax.text(x, y, str(driver_id), ha='center', va='center',
                    fontsize=9, color=text_color, fontweight=fontweight)


def make_snapshot_figure(drivers, orders, current_step):
    """
    生成当前状态的静态 Figure（供 Streamlit 等嵌入使用）。
    调用前请设置 os.environ['RIDESIM_MPL_BACKEND']='Agg' 且在首次 import matplotlib 之前。
    """
    fig, ax = plt.subplots(figsize=(9, 9))
    setup_plot_axes(ax)
    _draw_frame(ax, drivers, orders, current_step)
    # 尽量压缩 figure 空白边距，便于 Web 布局中“吃满”可用区域
    fig.subplots_adjust(left=0.035, right=0.995, top=0.94, bottom=0.07)
    return fig


class Visualizer:
    def __init__(self):
        """初始化可视化窗口"""
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(9, 9))
        setup_plot_axes(self.ax)

    def _setup_axes(self):
        """设置坐标轴和网格"""
        setup_plot_axes(self.ax)

    def draw(self, drivers, orders, current_step):
        """绘制当前仿真状态"""
        self._setup_axes()
        _draw_frame(self.ax, drivers, orders, current_step)
        plt.draw()
        plt.pause(0.001)


_visualizer_instance = None


def get_visualizer():
    """懒加载可视化器，避免在无可视化场景下弹空白窗口。"""
    global _visualizer_instance
    if _visualizer_instance is None:
        _visualizer_instance = Visualizer()
    return _visualizer_instance
