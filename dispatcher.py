"""
dispatcher.py
订单调度算法
实现不同的订单分配策略
"""
from utils import manhattan_distance

def nearest_driver_dispatch(orders, drivers):
    """
    最近司机调度算法 (贪心算法)。
    遍历所有等待中的订单，为每个订单分配当前距离它最近的空闲司机。
    """
    # --- 新增关键步骤：标记所有等待订单为“可调度” ---
    for order in orders:
        if order['status'] == 'waiting':
            order['ready_for_dispatch'] = True
    # ---------------------------------------------

    idle_drivers = [d for d in drivers if d['status'] == 'idle']
    if not idle_drivers:
        return

    # 为每个等待中的订单寻找司机
    for order in orders:
        # --- 修改条件：只有“可调度”的等待订单才处理 ---
        if order['status'] != 'waiting' or not order.get('ready_for_dispatch', True):
            continue

        # --- 计算订单费用（基于曼哈顿距离）---
        distance = manhattan_distance(order['start_x'], order['start_y'],
                                      order['end_x'], order['end_y'])
        order['fare'] = distance * 3  # 假设每单位距离价格是3

        # --- 寻找最近的司机 ---
        nearest_driver = None
        min_dist = float('inf')  # 初始化为无穷大

        for driver in idle_drivers:
            dist = manhattan_distance(order['start_x'], order['start_y'],
                                      driver['x'], driver['y'])
            if dist < min_dist:
                min_dist = dist
                nearest_driver = driver

        # --- 执行分配 ---
        if nearest_driver:
            nearest_driver['status'] = 'to_pickup'
            nearest_driver['current_order'] = order['id']
            order['status'] = 'picked_up'

            # 从空闲列表移除，避免被重复分配
            idle_drivers.remove(nearest_driver)

            from config import DEBUG
            if DEBUG:
                print(f"  调度: 订单{order['id']} (距司机{nearest_driver['id']} {min_dist}格) -> 司机{nearest_driver['id']}")

        # 如果没有更多空闲司机，结束本轮分配
        if not idle_drivers:
            break