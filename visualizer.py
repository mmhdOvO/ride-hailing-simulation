"""
visualizer.py
仿真过程可视化
使用Matplotlib绘制动态网格图
"""
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from config import GRID_SIZE, PLOT_DRIVER_NUM

# 设置Matplotlib使用支持交互的后端 (重要！)
import matplotlib
matplotlib.use('TkAgg')  # 如果报错，可以尝试 'Qt5Agg'

class Visualizer:
    def __init__(self):
        """初始化可视化窗口"""
        plt.ion()  # 打开交互模式
        self.fig, self.ax = plt.subplots(figsize=(9, 9))
        self.fig.canvas.manager.set_window_title('网约车仿真系统 - 第一阶段')
        self._setup_axes()

    def _setup_axes(self):
        """设置坐标轴和网格"""
        self.ax.clear()
        self.ax.set_xlim(-0.5, GRID_SIZE - 0.5)
        self.ax.set_ylim(-0.5, GRID_SIZE - 0.5)
        self.ax.set_aspect('equal')  # 确保每个格子是正方形
        self.ax.set_xticks(range(GRID_SIZE))
        self.ax.set_yticks(range(GRID_SIZE))
        self.ax.grid(True, linestyle=':', color='gray', alpha=0.5)
        self.ax.set_xlabel('X坐标')
        self.ax.set_ylabel('Y坐标')
        self.ax.invert_yaxis()  # 让(0,0)在左上角，符合矩阵习惯

    def draw(self, drivers, orders, current_step):
        """绘制当前仿真状态"""
        self._setup_axes()
        self.ax.set_title(f'网约车仿真 - 时间步: {current_step}')

         # 1. 绘制订单
        for order in orders:
            # 状态1: 等待中 - 红色实心圆
            if order['status'] == 'waiting':
                start_circle = patches.Circle((order['start_x'], order['start_y']),
                                              0.25, color='red', alpha=0.9, zorder=8)
                self.ax.add_patch(start_circle)
                self.ax.text(order['start_x'], order['start_y']-0.4,
                            f"O{order['id']}", ha='center', va='center',
                            fontsize=8, color='darkred', fontweight='bold')
            
            # 状态2: 已接单（司机正在赶来） - 橙色空心圆
            elif order['status'] == 'picked_up':
                # 使用圆圈，但设置为空心，表示订单已被领取，正在处理中
                start_circle = patches.Circle((order['start_x'], order['start_y']),
                                              0.28, linewidth=2, 
                                              edgecolor='orange', facecolor='none',
                                              alpha=0.9, zorder=7)
                self.ax.add_patch(start_circle)
                self.ax.text(order['start_x'], order['start_y']-0.4,
                            f"O{order['id']}", ha='center', va='center',
                            fontsize=8, color='darkorange', fontweight='bold')
                # 可以在旁边加个“(已接)”小字
                self.ax.text(order['start_x'], order['start_y']+0.4,
                            f"(已接)", ha='center', va='center',
                            fontsize=6, color='darkorange')

            # 为两种状态的订单都绘制终点虚线框
            if order['status'] in ['waiting', 'picked_up']:
                end_rect = patches.Rectangle((order['end_x']-0.35, order['end_y']-0.35),
                                             0.7, 0.7, linewidth=1.5,
                                             edgecolor='red', facecolor='none',
                                             linestyle='--', alpha=0.4)
                self.ax.add_patch(end_rect)

        # 2. 绘制司机
        for driver in drivers:
            # 根据状态决定颜色
            color_map = {'idle': 'blue', 'to_pickup': 'orange', 'on_trip': 'green'}
            color = color_map.get(driver['status'], 'black')

            # 司机当前位置 - 大圆点
            driver_circle = patches.Circle((driver['x'], driver['y']),
                                           0.35, color=color, alpha=0.8, zorder=10)
            self.ax.add_patch(driver_circle)

            # 显示司机编号
            if PLOT_DRIVER_NUM:
                self.ax.text(driver['x'], driver['y'],
                            str(driver['id']), ha='center', va='center',
                            fontsize=9, color='white', fontweight='bold')

        plt.draw()
        plt.pause(0.001)  # 短暂暂停，让图像得以更新

# 创建全局可视化器实例
visualizer = Visualizer()