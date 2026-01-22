"""
driver_engine.py
司机移动与状态更新引擎
"""
def move_driver_towards(driver, target_x, target_y):
    """
    让司机向目标坐标移动一格（曼哈顿距离）。
    返回 True 如果司机已经到达目标，否则返回 False。
    """
    # 记录移动前的位置
    driver['history'].append((driver['x'], driver['y']))

    # 如果已在目标点，无需移动
    if driver['x'] == target_x and driver['y'] == target_y:
        return True

    # 曼哈顿移动：先横向（X轴），后纵向（Y轴）
    if driver['x'] < target_x:
        driver['x'] += 1
    elif driver['x'] > target_x:
        driver['x'] -= 1
    elif driver['y'] < target_y:
        driver['y'] += 1
    elif driver['y'] > target_y:
        driver['y'] -= 1

    driver['total_distance'] += 1
    return False  # 尚未到达

def update_driver(driver, all_orders):
    """根据司机的当前状态，更新其位置和状态。"""
    # 状态1: 空闲，什么都不做
    if driver['status'] == 'idle':
        driver['history'].append((driver['x'], driver['y']))  # 记录停留
        return

    # 状态2 & 3: 去接客 或 送客中，需要找到对应的订单
    target_order = None
    for order in all_orders:
        if order['id'] == driver['current_order']:
            target_order = order
            break

    if not target_order:  # 订单意外消失，恢复空闲
        driver['status'] = 'idle'
        driver['current_order'] = None
        return

    # 根据状态决定移动目标
    if driver['status'] == 'to_pickup':
        target_x, target_y = target_order['start_x'], target_order['start_y']
        arrived = move_driver_towards(driver, target_x, target_y)
        if arrived:
            driver['status'] = 'on_trip'  # 到达起点，变更为送客状态
            from config import DEBUG
            if DEBUG:
                print(f"  司机{driver['id']} 已接到订单{target_order['id']}")

    elif driver['status'] == 'on_trip':
        target_x, target_y = target_order['end_x'], target_order['end_y']
        arrived = move_driver_towards(driver, target_x, target_y)
        if arrived:
            # 完成订单！
            target_order['status'] = 'completed'
            driver['revenue'] += target_order['fare']
            driver['status'] = 'idle'
            driver['current_order'] = None
            from config import DEBUG
            if DEBUG:
                print(f"  司机{driver['id']} 完成订单{target_order['id']}，收入 +{target_order['fare']}元")