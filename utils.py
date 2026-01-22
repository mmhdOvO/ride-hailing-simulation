"""
utils.py
通用工具函数
"""
import random
from config import RANDOM_SEED, GRID_SIZE

# 设置随机种子，确保结果可复现
random.seed(RANDOM_SEED)

def manhattan_distance(x1, y1, x2, y2):
    """计算两点间的曼哈顿距离。这是网格世界中的移动距离。"""
    return abs(x1 - x2) + abs(y1 - y2)

def print_grid(drivers, orders):
    """在控制台打印当前网格的文本地图，用于快速调试。"""
    # 初始化空网格
    grid = [[' . ' for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]

    # 标记订单起点 (O)
    for order in orders:
        if order['status'] == 'waiting':
            x, y = order['start_x'], order['start_y']
            grid[y][x] = ' O '

    # 标记司机位置 (D)
    for driver in drivers:
        x, y = driver['x'], driver['y']
        # 如果该格有订单，显示为司机接单状态
        if grid[y][x] == ' O ':
            grid[y][x] = f'D{driver["id"]}O'
        else:
            grid[y][x] = f' D{driver["id"]}' if driver['id'] < 10 else f'D{driver["id"]}'

    # 打印带边框的网格
    print('+' + '---' * GRID_SIZE + '+')
    for row in grid:
        print('|' + ''.join(row) + '|')
    print('+' + '---' * GRID_SIZE + '+\n')

def create_driver(driver_id):
    """创建并返回一个司机对象的字典。"""
    return {
        'id': driver_id,
        'x': random.randint(0, GRID_SIZE - 1),
        'y': random.randint(0, GRID_SIZE - 1),
        'status': 'idle',        # 状态: 'idle'(空闲), 'to_pickup'(去接客), 'on_trip'(送客中)
        'current_order': None,   # 当前承接的订单ID
        'revenue': 0,            # 总收入
        'total_distance': 0,     # 总行驶距离
        'history': []            # 历史位置记录，用于可视化轨迹
    }

def generate_order(order_id):
    """生成并返回一个随机订单对象的字典。"""
    # 确保起点和终点不相同
    start_x, start_y = random.randint(0, GRID_SIZE - 1), random.randint(0, GRID_SIZE - 1)
    end_x, end_y = start_x, start_y
    while end_x == start_x and end_y == start_y:
        end_x, end_y = random.randint(0, GRID_SIZE - 1), random.randint(0, GRID_SIZE - 1)

    return {
        'id': order_id,
        'start_x': start_x,
        'start_y': start_y,
        'end_x': end_x,
        'end_y': end_y,
        'status': 'waiting',     # 状态: 'waiting'(等待), 'picked_up'(已接单), 'completed'(已完成)
        'generation_step': 0,    # 订单生成的仿真步
        'waiting_steps': 0,      # 已等待的步数
        'fare': 0,               # 订单费用，将由调度算法计算
        'ready_for_dispatch': False  # 新增！初始为不可调度
    }