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
from .utils import driver as drv


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
    ax.set_xlim(-0.5, config.GRID_SIZE - 0.5)
    ax.set_ylim(-0.5, config.GRID_SIZE - 0.5)
    ax.set_aspect('equal')
    ax.set_xticks(range(config.GRID_SIZE))
    ax.set_yticks(range(config.GRID_SIZE))
    ax.grid(True, linestyle=':', color='gray', alpha=0.5)
    ax.set_xlabel('X坐标')
    ax.set_ylabel('Y坐标')
    ax.invert_yaxis()

    if config.USE_ZONES:
        residential = patches.Circle(
            (config.RESIDENTIAL_CENTER_X, config.RESIDENTIAL_CENTER_Y),
            config.RESIDENTIAL_RADIUS,
            linewidth=1.5,
            edgecolor='steelblue',
            facecolor='lightskyblue',
            alpha=0.12,
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
            color='steelblue',
            fontweight='bold',
            zorder=2,
        )

        work_area = patches.Circle(
            (config.WORK_AREA_CENTER_X, config.WORK_AREA_CENTER_Y),
            config.WORK_AREA_RADIUS,
            linewidth=1.5,
            edgecolor='saddlebrown',
            facecolor='navajowhite',
            alpha=0.15,
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
            color='saddlebrown',
            fontweight='bold',
            zorder=2,
        )

    font = _legend_font()
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10, label='订单-等待中'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='none', markeredgecolor='orange', markeredgewidth=2, markersize=10, label='订单-已接(赶往)'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='blue', markersize=10, label='司机-空闲'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', markersize=10, label='司机-去接'),
        Line2D([0], [0], marker='o', color='w', markerfacecolor='green', markersize=10, label='司机-送客'),
        patches.Patch(facecolor='lightskyblue', edgecolor='steelblue', alpha=0.25, label='居民区范围'),
        patches.Patch(facecolor='navajowhite', edgecolor='saddlebrown', alpha=0.30, label='工作区范围'),
    ]
    if config.DISTINGUISH_LLM_IN_VIZ:
        legend_elements.insert(
            5,
            Line2D([0], [0], marker='o', color='w', markerfacecolor='purple', markersize=10, label='LLM司机'),
        )
    leg = ax.legend(handles=legend_elements, loc='upper right')
    for text in leg.get_texts():
        text.set_fontproperties(font)


def _draw_frame(ax, drivers, orders, current_step):
    """在已 setup 的坐标轴上绘制订单与司机。"""
    ratio = current_step / max(1, config.SIMULATION_STEPS)
    if config.USE_TIME_PERIODS and config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END:
        period_label = "早高峰"
        period_color = "crimson"
    elif config.USE_TIME_PERIODS and config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END:
        period_label = "晚高峰"
        period_color = "darkorange"
    else:
        period_label = "平峰"
        period_color = "dimgray"

    ax.set_title(f'网约车仿真 - 时间步: {current_step} | 时段: {period_label}')
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
        bbox=dict(boxstyle='round,pad=0.25', facecolor='white', edgecolor=period_color, alpha=0.85),
        zorder=30,
    )

    for order in orders:
        if order['status'] == 'waiting':
            start_circle = patches.Circle((order['start_x'], order['start_y']),
                                          0.25, color='red', alpha=0.9, zorder=8)
            ax.add_patch(start_circle)
            ax.text(order['start_x'], order['start_y'] - 0.4,
                    f"O{order['id']}", ha='center', va='center',
                    fontsize=8, color='darkred', fontweight='bold')

        elif order['status'] == 'to_pickup':
            start_circle = patches.Circle((order['start_x'], order['start_y']),
                                          0.28, linewidth=2,
                                          edgecolor='orange', facecolor='none',
                                          alpha=0.9, zorder=7)
            ax.add_patch(start_circle)
            ax.text(order['start_x'], order['start_y'] - 0.4,
                    f"O{order['id']}", ha='center', va='center',
                    fontsize=8, color='darkorange', fontweight='bold')
            ax.text(order['start_x'], order['start_y'] + 0.4,
                    f"(赶往)", ha='center', va='center',
                    fontsize=6, color='darkorange')

        if order['status'] in ['waiting', 'to_pickup']:
            end_rect = patches.Rectangle((order['end_x'] - 0.35, order['end_y'] - 0.35),
                                         0.7, 0.7, linewidth=1.5,
                                         edgecolor='red', facecolor='none',
                                         linestyle='--', alpha=0.4)
            ax.add_patch(end_rect)

    for driver in drivers:
        status = drv.status(driver)
        x, y = drv.x(driver), drv.y(driver)
        driver_id = drv.driver_id(driver)
        is_llm = drv.is_llm(driver)

        color_map = {'idle': 'blue', 'to_pickup': 'orange', 'on_trip': 'green'}
        color = color_map.get(status, 'black')
        if is_llm and config.DISTINGUISH_LLM_IN_VIZ:
            color = 'purple'

        driver_circle = patches.Circle((x, y), 0.35, color=color, alpha=0.8, zorder=10)
        ax.add_patch(driver_circle)

        if config.PLOT_DRIVER_NUM:
            highlight_llm = is_llm and config.DISTINGUISH_LLM_IN_VIZ
            text_color = 'yellow' if highlight_llm else 'white'
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
