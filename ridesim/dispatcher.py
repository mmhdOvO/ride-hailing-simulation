"""
dispatcher.py
订单调度算法 - 使用统一API简化
"""
import random

from . import config
from .utils import manhattan_distance, shortest_road_distance
from .utils import driver as drv


def select_order_by_strategy(driver, orders):
    """
    普通司机的基线选单逻辑（贪心）：
    效率 = 订单收入 / 接驾距离
    返回: 选中的订单或None
    """
    idle_orders = [o for o in orders if o['status'] == 'waiting' and o.get('ready_for_dispatch', True)]
    if not idle_orders:
        return None
    
    pos = drv.position(driver)
    best_order = None
    best_efficiency = -1
    
    for order in idle_orders:
        road_dist = shortest_road_distance(pos[0], pos[1], order['start_x'], order['start_y'])
        dist = road_dist if road_dist is not None else manhattan_distance(pos[0], pos[1], order['start_x'], order['start_y'])
        fare = order.get('fare', 0)
        efficiency = fare / max(dist, 1)  # 每格收入
        if efficiency > best_efficiency:
            best_efficiency = efficiency
            best_order = order
    
    return best_order


def resolve_conflicts(selections):
    """
    处理多个司机选择同一订单的冲突。
    selections: [{'driver': driver, 'order': order}, ...]
    返回:
    - 已确认分配映射 {order_id: driver}

    说明：
    - 当前冲突策略是随机分配，作为中性基线；
    - 若做平台策略升级，可在这里替换为更复杂规则。
    """
    order_to_drivers = {}
    
    for sel in selections:
        if sel['order'] is None:
            continue
        oid = sel['order']['id']
        if oid not in order_to_drivers:
            order_to_drivers[oid] = []
        order_to_drivers[oid].append({'driver': sel['driver'], 'order': sel['order']})
    
    final_assignments = {}
    
    for oid, driver_list in order_to_drivers.items():
        if len(driver_list) == 1:
            final_assignments[oid] = driver_list[0]['driver']
            if config.DEBUG:
                print(f"  订单{oid} -> 司机{drv.driver_id(driver_list[0]['driver'])} (无冲突)")
        else:
            chosen = random.choice(driver_list)
            final_assignments[oid] = chosen['driver']
            if config.DEBUG:
                names = [drv.driver_id(d['driver']) for d in driver_list]
                print(f"  订单{oid} 冲突: 司机{names} -> 随机分配给司机{drv.driver_id(chosen['driver'])}")
    
    return final_assignments


def dispatch_with_conflict_resolution(llm_drivers, normal_drivers, orders, llm_decisions, normal_strategy='nearest'):
    """
    公平调度：所有司机同时选单，冲突后统一分配。
    llm_decisions: {driver_id: {'driver', 'decision', 'order'}} LLM司机的决策结果
    normal_strategy: 普通司机选单策略 ('nearest', 'random', 'round_robin')

    设计意图：
    - 先收集意向，再统一分配，可避免“先执行者占优”的时间顺序偏差。
    """
    selections = []
    
    for driver_id, info in llm_decisions.items():
        driver = info['driver']
        chosen_order = info['order']
        if drv.status(driver) == 'idle' and chosen_order:
            selections.append({'driver': driver, 'order': chosen_order})
    
    waiting_orders = [o for o in orders if o['status'] == 'waiting' and o.get('ready_for_dispatch', True)]
    
    idx = 0
    if normal_strategy == 'random':
        import random as random_module
        random_module.shuffle(waiting_orders)
    
    for i, driver in enumerate(normal_drivers):
        if drv.status(driver) != 'idle':
            continue
        
        if normal_strategy == 'nearest':
            chosen_order = select_order_by_strategy(driver, orders)
        elif normal_strategy == 'random':
            chosen_order = waiting_orders[idx] if waiting_orders and idx < len(waiting_orders) else None
            idx += 1
        elif normal_strategy == 'round_robin':
            chosen_order = waiting_orders[i % len(waiting_orders)] if waiting_orders else None
        else:
            chosen_order = select_order_by_strategy(driver, orders)
        
        if chosen_order:
            selections.append({'driver': driver, 'order': chosen_order})
    
    assignments = resolve_conflicts(selections)
    
    for order_id, driver in assignments.items():
        for order in orders:
            if order['id'] == order_id and order['status'] == 'waiting':
                drv.set_status(driver, 'to_pickup')
                drv.set_current_order(driver, order_id)
                order['status'] = 'to_pickup'
                if config.DEBUG:
                    print(f"  最终分配: 订单{order_id} -> 司机{drv.driver_id(driver)}")
                break
