"""
simulation.py
仿真主循环与流程控制 - 优化版
"""
import random
import time
from config import *
from utils import create_driver, generate_order, print_grid
from dispatcher import nearest_driver_dispatch
from driver_engine import update_driver

class Simulation:
    def __init__(self):
        """初始化仿真世界"""
        print("="*50)
        print("网约车仿真系统 - 第一阶段：基础仿真")
        print(f"配置：{GRID_SIZE}x{GRID_SIZE}网格，{NUM_DRIVERS}名司机，{SIMULATION_STEPS}个时间步")
        print("="*50)

        random.seed(RANDOM_SEED)
        self.drivers = []
        self.orders = []
        self.current_step = 0
        self.order_counter = 0
        self.is_running = True
        
        self._initialize_drivers()
        print("提示：仿真已初始化。使用 main_interactive.py 进入交互模式。")

    def _initialize_drivers(self):
        """初始化所有司机"""
        self.drivers = [create_driver(i) for i in range(NUM_DRIVERS)]
        print(f"初始化完成：{len(self.drivers)}名司机已就位。\n")

    def _generate_orders(self):
        """根据概率生成新订单"""
        for _ in range(GRID_SIZE * GRID_SIZE):
            if random.random() < ORDER_PROBABILITY / (GRID_SIZE * GRID_SIZE):
                new_order = generate_order(self.order_counter)
                new_order['generation_step'] = self.current_step
                self.orders.append(new_order)
                self.order_counter += 1
                if DEBUG:
                    print(f"  新订单{new_order['id']}: 从({new_order['start_x']},{new_order['start_y']}) "
                          f"到({new_order['end_x']},{new_order['end_y']})")

    def _update_orders_waiting_time(self):
        """更新所有等待中订单的等待时间"""
        for order in self.orders:
            if order['status'] == 'waiting':
                order['waiting_steps'] += 1

    def _execute_one_step(self, is_interactive=False):
        """
        执行单个仿真步的核心逻辑（私有方法）
        is_interactive: 是否为交互模式（控制是否自动延迟）
        """
        # 1. 生成新订单
        self._generate_orders()
        
        # 2. 调度：将等待订单分配给司机
        nearest_driver_dispatch(self.orders, self.drivers)
        
        # 3. 更新所有司机（移动、状态变更）
        for driver in self.drivers:
            update_driver(driver, self.orders)
        
        # 4. 更新订单等待时间
        self._update_orders_waiting_time()
        
        # 5. 打印状态（如果开启调试）
        if DEBUG:
            self._print_step_status()
        
        # 6. 可视化（如果开启）
        if VISUALIZE:
            from visualizer import visualizer
            visualizer.draw(self.drivers, self.orders, self.current_step)
            # 交互模式下，延迟由用户控制；自动模式下，使用配置的延迟
            if not is_interactive:
                time.sleep(STEP_DELAY)
        
        self.current_step += 1

    def get_status_summary(self):
        """获取当前仿真状态的摘要"""
        idle = sum(1 for d in self.drivers if d['status'] == 'idle')
        waiting = sum(1 for o in self.orders if o['status'] == 'waiting')
        completed = sum(1 for o in self.orders if o['status'] == 'completed')
        
        return {
            'step': self.current_step,
            'drivers': {
                'total': len(self.drivers),
                'idle': idle,
                'busy': len(self.drivers) - idle
            },
            'orders': {
                'total': len(self.orders),
                'waiting': waiting,
                'in_progress': len(self.orders) - waiting - completed,
                'completed': completed
            }
        }

    def _print_step_status(self):
        """打印当前时间步的摘要信息"""
        status = self.get_status_summary()
        
        print(f"[步 {status['step']:3d}] | "
              f"司机: 空闲{status['drivers']['idle']:2d} 接客{status['drivers']['busy']:2d} | "
              f"订单: 等待{status['orders']['waiting']:2d} 进行中{status['orders']['in_progress']:2d} 完成{status['orders']['completed']:2d}")
        
        # 每10步或在最后一步打印一次网格
        if self.current_step % 10 == 0 or self.current_step == SIMULATION_STEPS - 1:
            print_grid(self.drivers, self.orders)

    def step(self):
        """
        执行单个仿真步（用于交互模式）。
        返回值：如果仿真已到达设定步数，返回False，否则返回True。
        """
        if self.current_step >= SIMULATION_STEPS:
            print(f"\n已达到预设的总步数 ({SIMULATION_STEPS})，仿真结束。")
            self.is_running = False
            return False
        
        self._execute_one_step(is_interactive=True)
        return True
    
    def run_step(self):
        """
        执行一个完整的仿真步（用于原来的run方法）。
        """
        self._execute_one_step(is_interactive=False)

    def run(self):
        """运行完整仿真（调用修改后的run_step）"""
        print("仿真开始... (可按Ctrl+C中断)")
        start_time = time.time()

        try:
            for _ in range(SIMULATION_STEPS):
                self.run_step()
        except KeyboardInterrupt:
            print("\n\n仿真被用户中断。")
        finally:
            elapsed = time.time() - start_time
            self._print_final_report(elapsed)

            # 保持可视化窗口打开
            if VISUALIZE:
                print("\n关闭图形窗口以退出程序...")
                import matplotlib.pyplot as plt
                plt.ioff()
                plt.show()

    def auto_run(self):
        """
        自动运行直到结束（用于交互模式的自动运行选项）。
        """
        print(f"自动运行开始，将连续执行 {SIMULATION_STEPS - self.current_step} 步... (按Ctrl+C可强制中断)")
        start_time = time.time()
        
        try:
            while self.current_step < SIMULATION_STEPS and self.is_running:
                # 注意：这里调用的是 step() 方法，它会返回是否继续
                if not self.step():
                    break
        except KeyboardInterrupt:
            print("\n自动运行被用户中断。")
        finally:
            elapsed = time.time() - start_time
            self._print_final_report(elapsed)

    def is_finished(self):
        """判断仿真是否已完成（辅助方法）"""
        return self.current_step >= SIMULATION_STEPS

    def collect_statistics(self):
        """收集当前仿真的统计数据"""
        completed_orders = [o for o in self.orders if o['status'] == 'completed']
        
        stats = {
            'total_orders': len(self.orders),
            'completed_orders': len(completed_orders),
            'completion_rate': len(completed_orders) / max(1, len(self.orders)) * 100,
            'total_revenue': sum(d['revenue'] for d in self.drivers),
            'total_distance': sum(d['total_distance'] for d in self.drivers),
            'driver_stats': []
        }
        
        if completed_orders:
            stats['avg_waiting_time'] = sum(o['waiting_steps'] for o in completed_orders) / len(completed_orders)
        
        # 收集每个司机的详细数据
        for driver in self.drivers:
            stats['driver_stats'].append({
                'id': driver['id'],
                'revenue': driver['revenue'],
                'distance': driver['total_distance'],
                'final_position': (driver['x'], driver['y'])
            })
        
        return stats

    def _print_final_report(self, elapsed_time):
        """打印仿真最终统计报告（使用统计方法）"""
        stats = self.collect_statistics()
        
        print("\n" + "="*55)
        print("仿真完成！最终统计报告")
        print("="*55)
        print(f"总耗时: {elapsed_time:.2f} 秒")
        print(f"总订单数: {stats['total_orders']}")
        print(f"完成订单数: {stats['completed_orders']} ({stats['completion_rate']:.1f}%)")
        print(f"司机总收入: {stats['total_revenue']} 元")
        print(f"总行驶距离: {stats['total_distance']} 格")
        
        if 'avg_waiting_time' in stats:
            print(f"订单平均等待时间: {stats['avg_waiting_time']:.1f} 步")
        
        print("\n--- 司机收入排行榜 ---")
        # 按收入排序司机
        sorted_drivers = sorted(self.drivers, key=lambda d: d['revenue'], reverse=True)
        for i, driver in enumerate(sorted_drivers[:5]):
            print(f"  {i+1}. 司机{driver['id']:2d}: {driver['revenue']:4d}元 | "
                  f"行驶{driver['total_distance']:3d}格 | "
                  f"最后位置({driver['x']},{driver['y']})")

    def export_data(self, filename=None):
        """
        导出仿真数据到文件
        filename: 如果不指定，使用默认文件名
        """
        if filename is None:
            filename = f"simulation_data_{int(time.time())}.json"
        
        import json
        data = {
            'config': {
                'grid_size': GRID_SIZE,
                'num_drivers': NUM_DRIVERS,
                'simulation_steps': SIMULATION_STEPS,
                'order_probability': ORDER_PROBABILITY,
                'random_seed': RANDOM_SEED
            },
            'statistics': self.collect_statistics(),
            'final_state': {
                'step': self.current_step,
                'drivers': self.drivers,
                'orders': self.orders
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"数据已导出到: {filename}")
        return filename