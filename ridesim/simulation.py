"""
simulation.py
仿真主循环与流程控制 - 优化版（兼容LLM司机）
"""
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .dispatcher import dispatch_with_conflict_resolution
from .driver_engine import LLMDriver, update_driver
from .utils import (
    create_driver,
    generate_order,
    get_time_period_multiplier,
    manhattan_distance,
    print_grid,
    snap_to_road,
)
from .utils import driver as drv


class Simulation:
    def __init__(self):
        """
        初始化仿真世界（支持LLM司机）。

        设计说明：
        - 仿真核心状态（司机、订单、步数）都由 Simulation 托管；
        - 司机可由普通规则司机与 LLM 司机混合组成；
        - 每次初始化都会基于 RANDOM_SEED 固定随机流，便于复现实验结果。
        """
        print("="*50)
        print("网约车仿真系统 - 第二阶段：LLM集成")
        print(f"配置：{config.GRID_SIZE}x{config.GRID_SIZE}网格，{config.NUM_DRIVERS}名司机，{config.SIMULATION_STEPS}个时间步")
        print("="*50)

        if getattr(config, "AUTO_SCALE_ZONES", False):
            config.auto_scale_zone_params()

        random.seed(config.RANDOM_SEED)
        self.drivers = []
        self.orders = []
        self.current_step = 0
        self.order_counter = 0
        self.is_running = True
        self.use_llm = config.USE_LLM_DRIVERS
        self._visualizer = None

        if self.use_llm:
            num_llm = min(config.NUM_LLM_DRIVERS, config.NUM_DRIVERS)
            for i in range(num_llm):
                self.drivers.append(LLMDriver(i))
            for i in range(num_llm, config.NUM_DRIVERS):
                self.drivers.append(create_driver(i))
            print(f"初始化完成：{num_llm}名LLM司机 + {config.NUM_DRIVERS - num_llm}名普通司机")
        else:
            self.drivers = [create_driver(i) for i in range(config.NUM_DRIVERS)]
            print(f"初始化完成：{len(self.drivers)}名普通司机")
        
        print("提示：仿真已初始化。使用 main.py 进入交互模式。")
        # 启动即渲染 step=0 首帧，避免用户必须先执行一步才看到窗口。
        self._visualize_step(is_interactive=True)

    def _generate_orders(self):
        """
        根据概率、时段和区域生成新订单。

        注意：
        - 收尾阶段（最后10步）停止发单，给系统留出“消化在途订单”的窗口；
        - 每步按网格面积做稀疏采样，避免单步订单暴涨。
        """
        if self.current_step >= config.SIMULATION_STEPS - 10:
            if config.DEBUG and self.current_step == config.SIMULATION_STEPS - 10:
                print("  已停止生成新订单，进入收尾阶段")
            return
        
        time_multiplier = get_time_period_multiplier(self.current_step)
        
        for _ in range(config.GRID_SIZE * config.GRID_SIZE):
            if random.random() < (config.ORDER_PROBABILITY * time_multiplier) / (config.GRID_SIZE * config.GRID_SIZE):
                new_order = generate_order(self.order_counter, self.current_step)
                new_order['generation_step'] = self.current_step
                if config.FORCE_ONE_STEP_BEFORE_DISPATCH:
                    new_order['ready_for_dispatch'] = False
                self.orders.append(new_order)
                self.order_counter += 1
                if config.DEBUG:
                    print(f"  新订单{new_order['id']}: 从({new_order['start_x']},{new_order['start_y']}) "
                          f"到({new_order['end_x']},{new_order['end_y']})")

    def add_passenger_order(self, start_x: int, start_y: int, end_x: int, end_y: int) -> dict:
        """
        乘客端手动下单：插入一笔等待中的订单（与随机生成订单字段一致）。
        若开启 FORCE_ONE_STEP_BEFORE_DISPATCH，则本步不可抢，下一步才可抢。
        """
        gx = config.GRID_SIZE - 1
        for x, y in ((start_x, start_y), (end_x, end_y)):
            if not (0 <= x <= gx and 0 <= y <= gx):
                raise ValueError(f"坐标越界: ({x},{y})，有效范围 0..{gx}")

        start_x, start_y = snap_to_road(start_x, start_y)
        end_x, end_y = snap_to_road(end_x, end_y)
        dist = manhattan_distance(start_x, start_y, end_x, end_y)
        if dist == 0:
            raise ValueError("起点与终点吸附到道路后重合，请更换坐标")

        oid = self.order_counter
        order = {
            'id': oid,
            'start_x': start_x,
            'start_y': start_y,
            'end_x': end_x,
            'end_y': end_y,
            'status': 'waiting',
            'generation_step': self.current_step,
            'waiting_steps': 0,
            'fare': dist * 3,
            'distance': dist,
            'ready_for_dispatch': not getattr(config, 'FORCE_ONE_STEP_BEFORE_DISPATCH', False),
        }
        self.orders.append(order)
        self.order_counter += 1
        return order

    def _update_dispatch_readiness(self):
        """更新订单是否允许参与本步抢单。"""
        if not config.FORCE_ONE_STEP_BEFORE_DISPATCH:
            return
        for order in self.orders:
            if order['status'] == 'waiting' and not order.get('ready_for_dispatch', True):
                if order.get('generation_step', self.current_step) < self.current_step:
                    order['ready_for_dispatch'] = True

    def _update_orders_waiting_time(self):
        """更新所有等待中订单的等待时间"""
        for order in self.orders:
            if order['status'] == 'waiting':
                order['waiting_steps'] += 1

    def _prepare_drivers(self):
        """
        准备司机列表，区分 LLM 司机与普通司机。

        返回 all_driver_dicts 的目的是给 LLM 提供统一结构观察，
        这样无需关心对象类型差异（dict / LLMDriver）。
        """
        llm_drivers = [d for d in self.drivers if drv.is_llm(d)]
        normal_drivers = [d for d in self.drivers if not drv.is_llm(d)]
        all_driver_dicts = [drv.get_driver_dict(d) if drv.is_llm(d) else d for d in self.drivers]
        return llm_drivers, normal_drivers, all_driver_dicts
    
    def _collect_llm_decisions(self, llm_drivers, all_driver_dicts):
        """
        收集 LLM 司机决策（只收集，不落锁）。

        当前采用“先决策后统一分配”模式：
        - 先让所有司机并行提出意向；
        - 再统一冲突消解，避免先来后到偏差。

        若开启 LLM_PARALLEL_DECISIONS，各空闲 LLM 司机在本步内通过线程池同时调用 API，
        墙钟时间接近「最慢的一单」而非「各单之和」。
        """
        idle = [d for d in llm_drivers if drv.status(d) == 'idle']
        if not idle:
            return {}

        def collect_one(driver):
            did = drv.driver_id(driver)
            try:
                decision, selected_order = driver.decide_only(
                    self.orders, self.current_step, all_driver_dicts
                )
                return did, {
                    'driver': driver,
                    'decision': decision,
                    'order': selected_order,
                }
            except Exception as e:
                print(f"  司机{did}决策异常: {e}，本步按原地等待处理")
                return did, {
                    'driver': driver,
                    'decision': 'F',
                    'order': None,
                }

        if not getattr(config, 'LLM_PARALLEL_DECISIONS', True) or len(idle) == 1:
            llm_decisions = {}
            for d in idle:
                did, entry = collect_one(d)
                llm_decisions[did] = entry
            return llm_decisions

        cap = int(getattr(config, 'LLM_PARALLEL_MAX_WORKERS', 0) or 0)
        max_workers = len(idle) if cap <= 0 else min(len(idle), cap)
        max_workers = max(1, max_workers)

        llm_decisions = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(collect_one, d) for d in idle]
            for fut in as_completed(futures):
                did, entry = fut.result()
                llm_decisions[did] = entry
        return llm_decisions
    
    def _execute_llm_moves(self, llm_drivers, llm_decisions):
        """
        执行 LLM 司机动作。

        规则：
        - 如果该司机在冲突分配后仍空闲，则执行其决策动作；
        - 若该步无可执行决策，执行热点探索，减少纯随机游走。
        """
        for driver in llm_drivers:
            if drv.status(driver) == 'idle':
                info = llm_decisions.get(drv.driver_id(driver))
                if info:
                    driver.execute_decision(info['decision'], info['order'])
                else:
                    # 无订单时做“热点探索”而非随机游走
                    direction = self._get_hotspot_explore_direction(driver)
                    driver.move(direction)

    def _get_hotspot_explore_direction(self, driver):
        """根据时段把空闲LLM司机引导到潜在热点区域。"""
        x, y = drv.x(driver), drv.y(driver)
        ratio = self.current_step / max(1, config.SIMULATION_STEPS)

        # 早高峰偏居民区，晚高峰偏工作区，平峰偏城市中心
        if config.USE_TIME_PERIODS and config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END:
            tx, ty = config.RESIDENTIAL_CENTER_X, config.RESIDENTIAL_CENTER_Y
        elif config.USE_TIME_PERIODS and config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END:
            tx, ty = config.WORK_AREA_CENTER_X, config.WORK_AREA_CENTER_Y
        else:
            tx, ty = config.GRID_SIZE // 2, config.GRID_SIZE // 2

        if x < tx:
            return 'D'
        if x > tx:
            return 'E'
        if y < ty:
            return 'C'
        if y > ty:
            return 'B'
        return random.choice(['B', 'C', 'D', 'E'])
    
    def _update_busy_drivers(self):
        """更新所有非空闲司机的状态"""
        for driver in self.drivers:
            if drv.status(driver) != 'idle':
                update_driver(driver, self.orders, self.current_step)
    
    def _visualize_step(self, is_interactive):
        """可视化当前步骤"""
        if config.VISUALIZE:
            if self._visualizer is None:
                from .visualizer import get_visualizer
                self._visualizer = get_visualizer()
            self._visualizer.draw(self.drivers, self.orders, self.current_step)
            if not is_interactive:
                time.sleep(config.STEP_DELAY)
    
    def _execute_one_step(self, is_interactive=False):
        """
        执行单个仿真步（公平竞争版本）。

        处理顺序固定为：
        1) 生成订单
        2) 收集决策
        3) 冲突分配
        4) 执行动作并更新司机状态
        5) 更新等待时长与可视化

        固定顺序有助于保障实验可复现性。
        """
        self._update_dispatch_readiness()
        self._generate_orders()
        llm_drivers, normal_drivers, all_driver_dicts = self._prepare_drivers()
        llm_decisions = self._collect_llm_decisions(llm_drivers, all_driver_dicts)
        dispatch_with_conflict_resolution(
            llm_drivers, normal_drivers, self.orders, llm_decisions, config.NORMAL_STRATEGY
        )
        self._execute_llm_moves(llm_drivers, llm_decisions)
        self._update_busy_drivers()
        self._update_orders_waiting_time()
        if config.DEBUG:
            self._print_step_status()
        self._visualize_step(is_interactive)
        self.current_step += 1

    def get_status_summary(self):
        """获取当前仿真状态的摘要（使用统一API）"""
        idle = sum(1 for d in self.drivers if drv.status(d) == 'idle')
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
        if self.current_step % 10 == 0 or self.current_step == config.SIMULATION_STEPS - 1:
            print_grid(self.drivers, self.orders)

    def step(self):
        """执行单个仿真步（用于交互模式）。"""
        if self.current_step >= config.SIMULATION_STEPS:
            print(f"\n已达到预设的总步数 ({config.SIMULATION_STEPS})，仿真结束。")
            self._print_final_report(0)
            self.is_running = False
            return False
        self._execute_one_step(is_interactive=True)
        return True
    
    def run_step(self):
        """执行一个完整的仿真步（用于原来的run方法）。"""
        self._execute_one_step(is_interactive=False)

    def run(self):
        """运行完整仿真"""
        print("仿真开始... (可按Ctrl+C中断)")
        start_time = time.time()
        try:
            for _ in range(config.SIMULATION_STEPS):
                self.run_step()
        except KeyboardInterrupt:
            print("\n\n仿真被用户中断。")
        finally:
            elapsed = time.time() - start_time
            self._print_final_report(elapsed)
            if config.VISUALIZE:
                print("\n关闭图形窗口以退出程序...")
                import matplotlib.pyplot as plt
                plt.ioff()
                plt.show()

    def auto_run(self):
        """自动运行直到结束（用于交互模式的自动运行选项）。"""
        print(f"自动运行开始，将连续执行 {config.SIMULATION_STEPS - self.current_step} 步... (按Ctrl+C可强制中断)")
        start_time = time.time()
        try:
            while self.current_step < config.SIMULATION_STEPS and self.is_running:
                if not self.step():
                    break
        except KeyboardInterrupt:
            print("\n自动运行被用户中断。")
        finally:
            elapsed = time.time() - start_time
            self._print_final_report(elapsed)

    def collect_statistics(self):
        """
        收集当前仿真统计指标（平台效率 + 用户体验 + 司机公平性）。

        返回结构可直接用于：
        - 控制台最终报告
        - JSON 导出
        - 测试脚本自动对比
        """
        completed_orders = [o for o in self.orders if o['status'] == 'completed']
        revenues = [drv.revenue(d) for d in self.drivers]
        
        stats = {
            'total_orders': len(self.orders),
            'completed_orders': len(completed_orders),
            'completion_rate': len(completed_orders) / max(1, len(self.orders)) * 100,
            'total_revenue': sum(revenues),
            'total_distance': sum(drv.distance(d) for d in self.drivers),
            'driver_stats': []
        }
        
        if completed_orders:
            stats['avg_waiting_time'] = sum(o['waiting_steps'] for o in completed_orders) / len(completed_orders)
            stats['max_waiting_time'] = max(o['waiting_steps'] for o in completed_orders)
            stats['min_waiting_time'] = min(o['waiting_steps'] for o in completed_orders)
        
        if revenues:
            stats['avg_revenue'] = sum(revenues) / len(revenues)
            stats['max_revenue'] = max(revenues)
            stats['min_revenue'] = min(revenues)
            stats['revenue_gini'] = self._calculate_gini(revenues)
            stats['revenue_cv'] = self._calculate_cv(revenues)
        
        for d in self.drivers:
            stats['driver_stats'].append({
                'id': drv.driver_id(d),
                'revenue': drv.revenue(d),
                'distance': drv.distance(d),
                'final_position': drv.position(d)
            })
        
        return stats
    
    def _calculate_gini(self, values):
        """计算Gini系数（收入公平性）"""
        if not values or len(values) < 2:
            return 0.0
        values = sorted(values)
        n = len(values)
        if sum(values) == 0:
            return 0.0
        gini = sum((2 * (i + 1) - n - 1) * values[i] for i in range(n))
        return gini / (n * sum(values))
    
    def _calculate_cv(self, values):
        """计算变异系数（收入公平性）"""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return (variance ** 0.5) / mean

    def _print_final_report(self, elapsed_time):
        """打印仿真最终统计报告"""
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
            print(f"\n--- 用户体验指标 ---")
            print(f"平均等待时间: {stats['avg_waiting_time']:.1f} 步")
            print(f"最长等待时间: {stats['max_waiting_time']} 步")
            print(f"最短等待时间: {stats['min_waiting_time']} 步")
        
        if 'revenue_gini' in stats:
            print(f"\n--- 公平性指标 ---")
            print(f"Gini系数: {stats['revenue_gini']:.3f} (0=完全平等,1=完全不平等)")
            print(f"收入变异系数: {stats['revenue_cv']:.3f} (越小越公平)")
            print(f"收入极差: {stats['min_revenue']}-{stats['max_revenue']} 元")
        
        print("\n--- 司机收入排行榜 ---")
        sorted_drivers = sorted(self.drivers, key=lambda d: drv.revenue(d), reverse=True)
        for i, driver in enumerate(sorted_drivers):
            driver_type = " (LLM)" if drv.is_llm(driver) else ""
            print(f"  {i+1}. 司机{drv.driver_id(driver):2d}{driver_type}: {drv.revenue(driver):4d}元 | "
                  f"行驶{drv.distance(driver):3d}格 | "
                  f"最后位置({drv.x(driver)},{drv.y(driver)})")

    def _get_serializable_drivers(self):
        """获取可序列化的司机数据"""
        serializable_drivers = []
        for driver in self.drivers:
            if drv.is_llm(driver):
                driver_data = drv.get_driver_dict(driver)
                serializable_drivers.append({**driver_data, 'type': 'llm'})
            else:
                serializable_drivers.append({**driver, 'type': 'normal'})
        return serializable_drivers
    
    def export_data(self, filename=None):
        """导出仿真数据到文件"""
        if filename is None:
            filename = f"simulation_data_{int(time.time())}.json"
        
        data = {
            'config': {
                'grid_size': config.GRID_SIZE,
                'num_drivers': config.NUM_DRIVERS,
                'simulation_steps': config.SIMULATION_STEPS,
                'order_probability': config.ORDER_PROBABILITY,
                'random_seed': config.RANDOM_SEED
            },
            'statistics': self.collect_statistics(),
            'final_state': {
                'step': self.current_step,
                'drivers': self._get_serializable_drivers(),
                'orders': self.orders
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"数据已导出到: {filename}")
        return filename
