"""
utils.py
通用工具函数
"""
import math
import random
import threading
from collections import deque

from . import config

# 设置随机种子，确保结果可复现
random.seed(config.RANDOM_SEED)

_ROAD_CACHE = {"key": None, "mask": None}
_ROAD_DIST_CACHE = {}
_ROAD_DIST_LOCK = threading.Lock()

def manhattan_distance(x1, y1, x2, y2):
    """计算两点间的曼哈顿距离。这是网格世界中的移动距离。"""
    return abs(x1 - x2) + abs(y1 - y2)


def get_road_mask():
    """
    生成/缓存道路掩码（True=道路可通行）。
    """
    key = (
        config.GRID_SIZE,
        bool(getattr(config, "USE_ROAD_NETWORK", False)),
        int(getattr(config, "ROAD_SPACING", 4)),
        bool(getattr(config, "ROAD_BORDER_RING", True)),
        int(getattr(config, "RANDOM_SEED", 0)),
    )
    if _ROAD_CACHE["key"] == key and _ROAD_CACHE["mask"] is not None:
        return _ROAD_CACHE["mask"]

    n = config.GRID_SIZE
    if not getattr(config, "USE_ROAD_NETWORK", False):
        mask = [[True for _ in range(n)] for _ in range(n)]
    else:
        spacing = max(2, int(getattr(config, "ROAD_SPACING", 4)))
        rng = random.Random(config.RANDOM_SEED + 20260429)
        mask = [[False for _ in range(n)] for _ in range(n)]

        # 1) 不规则主干道：在基础间隔上加入抖动，形成不均匀街区
        verticals = []
        x = 0
        while x < n:
            jitter = rng.randint(-1, 1)
            vx = max(0, min(n - 1, x + jitter))
            verticals.append(vx)
            x += spacing + rng.randint(-1, 2)
        horizontals = []
        y = 0
        while y < n:
            jitter = rng.randint(-1, 1)
            hy = max(0, min(n - 1, y + jitter))
            horizontals.append(hy)
            y += spacing + rng.randint(-1, 2)

        # 增加一条近中心主干道，保证整体连通和观感
        verticals.append(n // 2)
        horizontals.append(n // 2)
        verticals = sorted(set(verticals))
        horizontals = sorted(set(horizontals))

        for vx in verticals:
            width = 1 + (1 if rng.random() < 0.25 else 0)  # 少量双车道主路
            for yy in range(n):
                for ox in range(width):
                    xx = min(n - 1, vx + ox)
                    mask[yy][xx] = True

        for hy in horizontals:
            width = 1 + (1 if rng.random() < 0.25 else 0)
            for xx in range(n):
                for oy in range(width):
                    yy = min(n - 1, hy + oy)
                    mask[yy][xx] = True

        # 2) 局部支路：短路段，打破“棋盘式均匀”
        branches = max(6, n // 3)
        for _ in range(branches):
            if rng.random() < 0.5 and verticals:
                vx = rng.choice(verticals)
                y0 = rng.randint(0, n - 1)
                lo = max(2, spacing // 2)
                hi = min(n - y0, spacing + 3)
                if lo <= hi:
                    seg_len = rng.randint(lo, hi)
                    for yy in range(y0, min(n, y0 + seg_len)):
                        mask[yy][vx] = True
            elif horizontals:
                hy = rng.choice(horizontals)
                x0 = rng.randint(0, n - 1)
                lo = max(2, spacing // 2)
                hi = min(n - x0, spacing + 3)
                if lo <= hi:
                    seg_len = rng.randint(lo, hi)
                    for xx in range(x0, min(n, x0 + seg_len)):
                        mask[hy][xx] = True

        if getattr(config, "ROAD_BORDER_RING", True):
            for i in range(n):
                mask[0][i] = True
                mask[n - 1][i] = True
                mask[i][0] = True
                mask[i][n - 1] = True

    _ROAD_CACHE["key"] = key
    _ROAD_CACHE["mask"] = mask
    _ROAD_DIST_CACHE.clear()
    return mask


def is_road(x, y):
    if not (0 <= x < config.GRID_SIZE and 0 <= y < config.GRID_SIZE):
        return False
    return get_road_mask()[y][x]


def snap_to_road(x, y):
    """
    将坐标吸附到最近道路格。
    """
    x = max(0, min(config.GRID_SIZE - 1, int(x)))
    y = max(0, min(config.GRID_SIZE - 1, int(y)))
    if is_road(x, y):
        return x, y

    q = deque([(x, y)])
    visited = {(x, y)}
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    while q:
        cx, cy = q.popleft()
        for dx, dy in dirs:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < config.GRID_SIZE and 0 <= ny < config.GRID_SIZE):
                continue
            if (nx, ny) in visited:
                continue
            if is_road(nx, ny):
                return nx, ny
            visited.add((nx, ny))
            q.append((nx, ny))
    return x, y


def get_road_neighbors(x, y):
    res = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if 0 <= nx < config.GRID_SIZE and 0 <= ny < config.GRID_SIZE and is_road(nx, ny):
            res.append((nx, ny))
    return res


def random_road_point():
    mask = get_road_mask()
    candidates = [(x, y) for y in range(config.GRID_SIZE) for x in range(config.GRID_SIZE) if mask[y][x]]
    if not candidates:
        return random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1)
    return random.choice(candidates)


def next_step_on_road(start_x, start_y, target_x, target_y):
    """
    计算道路网络上从 start 到 target 的下一步坐标。
    返回 None 表示不可达。
    """
    sx, sy = snap_to_road(start_x, start_y)
    tx, ty = snap_to_road(target_x, target_y)
    if (sx, sy) == (tx, ty):
        return sx, sy

    q = deque([(sx, sy)])
    parent = {(sx, sy): None}
    while q:
        cx, cy = q.popleft()
        if (cx, cy) == (tx, ty):
            break
        for nx, ny in get_road_neighbors(cx, cy):
            if (nx, ny) in parent:
                continue
            parent[(nx, ny)] = (cx, cy)
            q.append((nx, ny))

    if (tx, ty) not in parent:
        return None

    cur = (tx, ty)
    while parent[cur] is not None and parent[cur] != (sx, sy):
        cur = parent[cur]
    if parent[cur] is None:
        return sx, sy
    return cur


def shortest_road_distance(start_x, start_y, target_x, target_y):
    """
    返回道路网络上的最短步长（BFS）。
    若不可达，返回 None。
    """
    sx, sy = snap_to_road(start_x, start_y)
    tx, ty = snap_to_road(target_x, target_y)
    dist_key = (_ROAD_CACHE["key"], sx, sy, tx, ty)
    with _ROAD_DIST_LOCK:
        if dist_key in _ROAD_DIST_CACHE:
            return _ROAD_DIST_CACHE[dist_key]
        if (sx, sy) == (tx, ty):
            _ROAD_DIST_CACHE[dist_key] = 0
            return 0

    q = deque([(sx, sy, 0)])
    visited = {(sx, sy)}
    while q:
        cx, cy, dist = q.popleft()
        for nx, ny in get_road_neighbors(cx, cy):
            if (nx, ny) in visited:
                continue
            if (nx, ny) == (tx, ty):
                value = dist + 1
                with _ROAD_DIST_LOCK:
                    _ROAD_DIST_CACHE[dist_key] = value
                return value
            visited.add((nx, ny))
            q.append((nx, ny, dist + 1))
    with _ROAD_DIST_LOCK:
        _ROAD_DIST_CACHE[dist_key] = None
    return None

def print_grid(drivers, orders):
    """在控制台打印当前网格的文本地图，用于快速调试。"""
    # 初始化空网格
    grid = [[' . ' for _ in range(config.GRID_SIZE)] for _ in range(config.GRID_SIZE)]

    # 标记订单起点 (O)
    for order in orders:
        if order['status'] == 'waiting':
            x, y = order['start_x'], order['start_y']
            grid[y][x] = ' O '

    # 标记司机位置 (D) - 兼容普通司机和LLM司机
    for driver in drivers:
        # 获取司机坐标和ID（兼容两种类型）
        if isinstance(driver, dict):
            x, y = driver['x'], driver['y']
            driver_id = driver['id']
        else:
            # LLMDriver对象
            x, y = driver.driver['x'], driver.driver['y']
            driver_id = driver.driver['id']
        
        # 如果该格有订单，显示为司机接单状态
        if grid[y][x] == ' O ':
            grid[y][x] = f'D{driver_id}O'
        else:
            # 确保显示对齐
            if driver_id < 10:
                grid[y][x] = f' D{driver_id}'
            else:
                grid[y][x] = f'D{driver_id}'

    # 打印带边框的网格
    print('+' + '---' * config.GRID_SIZE + '+')
    for row in grid:
        print('|' + ''.join(row) + '|')
    print('+' + '---' * config.GRID_SIZE + '+\n')

def create_driver(driver_id):
    """创建并返回一个司机对象的字典。"""
    x, y = random_road_point()
    return {
        'id': driver_id,
        'x': x,
        'y': y,
        'status': 'idle',        # 状态: 'idle'(空闲), 'to_pickup'(去接客), 'on_trip'(送客中)
        'current_order': None,   # 当前承接的订单ID
        'revenue': 0,            # 总收入
        'total_distance': 0,     # 总行驶距离
        'history': []            # 历史位置记录，用于可视化轨迹
    }

def generate_order(order_id, current_step=0):
    """生成并返回一个随机订单对象的字典。"""
    # 根据区域和时段生成订单起点
    if config.USE_ZONES:
        start_x, start_y, end_x, end_y = _generate_location_with_zone(current_step)
    else:
        start_x, start_y = random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1)
        end_x, end_y = start_x, start_y
        while end_x == start_x and end_y == start_y:
            end_x, end_y = random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1)
    
    start_x, start_y = snap_to_road(start_x, start_y)
    end_x, end_y = snap_to_road(end_x, end_y)
    if end_x == start_x and end_y == start_y:
        ex, ey = random_road_point()
        if (ex, ey) != (start_x, start_y):
            end_x, end_y = ex, ey

    # 生成时即计算订单费用（确保LLM能看到真实价值）
    distance = manhattan_distance(start_x, start_y, end_x, end_y)
    fare = distance * 3

    return {
        'id': order_id,
        'start_x': start_x,
        'start_y': start_y,
        'end_x': end_x,
        'end_y': end_y,
        'status': 'waiting',
        'generation_step': 0,
        'waiting_steps': 0,
        'fare': fare,
        'distance': distance,
        'ready_for_dispatch': True
    }

def _generate_location_with_zone(current_step):
    """根据区域权重和时段生成订单起点和终点"""
    # 确定当前时段
    progress = current_step / config.SIMULATION_STEPS if config.SIMULATION_STEPS > 0 else 0
    is_morning = config.USE_TIME_PERIODS and (config.MORNING_PEAK_START <= progress < config.MORNING_PEAK_END)
    is_evening = config.USE_TIME_PERIODS and (config.EVENING_PEAK_START <= progress < config.EVENING_PEAK_END)
    
    # 根据时段决定起点区域
    if is_morning:
        # 早高峰：住宅区起点多（去工作）
        start_zone = 'residential'
    elif is_evening:
        # 晚高峰：工作区起点多（回家）
        start_zone = 'work'
    else:
        # 平峰期：随机
        start_zone = 'random'
    
    # 生成起点
    if start_zone == 'residential':
        start_x, start_y = _generate_in_circle(
            config.RESIDENTIAL_CENTER_X, 
            config.RESIDENTIAL_CENTER_Y, 
            config.RESIDENTIAL_RADIUS
        )
    elif start_zone == 'work':
        start_x, start_y = _generate_in_circle(
            config.WORK_AREA_CENTER_X, 
            config.WORK_AREA_CENTER_Y, 
            config.WORK_AREA_RADIUS
        )
    else:
        start_x, start_y = random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1)
    
    # 生成终点（与起点相反）
    if start_zone == 'residential':
        # 从居民区出发，去工作区
        end_x, end_y = _generate_in_circle(
            config.WORK_AREA_CENTER_X, 
            config.WORK_AREA_CENTER_Y, 
            config.WORK_AREA_RADIUS
        )
    elif start_zone == 'work':
        # 从工作区出发，回居民区
        end_x, end_y = _generate_in_circle(
            config.RESIDENTIAL_CENTER_X, 
            config.RESIDENTIAL_CENTER_Y, 
            config.RESIDENTIAL_RADIUS
        )
    else:
        # 平峰期随机终点
        end_x, end_y = random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1)
    
    # 确保起点和终点不同
    if end_x == start_x and end_y == start_y:
        end_x = (start_x + random.randint(5, 15)) % config.GRID_SIZE
        end_y = (start_y + random.randint(5, 15)) % config.GRID_SIZE
    
    return start_x, start_y, end_x, end_y

def _generate_in_circle(center_x, center_y, radius):
    """
    在圆形区域内【均匀】随机生成一点
    修正说明：
    1. 使用正确的极坐标转直角坐标公式
    2. 对半径开平方，保证圆形区域内点的分布均匀
    3. 移除无效循环，增加边界检查的鲁棒性
    """
    # 1. 生成极坐标（保证均匀分布）
    angle = random.uniform(0, 2 * math.pi)  # 角度：0 到 2π
    # 关键点：对 r 开平方，避免点聚集在圆心
    r = math.sqrt(random.uniform(0, 1)) * radius

    # 2. 极坐标转直角坐标
    x = center_x + r * math.cos(angle)
    y = center_y + r * math.sin(angle)

    # 3. 取整并限制在网格边界内
    x = int(round(x))  # 用 round() 比直接 int() 更合理
    y = int(round(y))
    
    # 确保不越界
    x = max(0, min(config.GRID_SIZE - 1, x))
    y = max(0, min(config.GRID_SIZE - 1, y))

    return x, y

def get_time_period_multiplier(current_step):
    """根据当前仿真步数获取时段倍数"""
    if not config.USE_TIME_PERIODS:
        return 1.0
    
    progress = current_step / config.SIMULATION_STEPS
    
    # 早高峰
    if config.MORNING_PEAK_START <= progress < config.MORNING_PEAK_END:
        return config.MORNING_PEAK_MULTIPLIER
    # 晚高峰
    elif config.EVENING_PEAK_START <= progress < config.EVENING_PEAK_END:
        return config.EVENING_PEAK_MULTIPLIER
    # 平峰期
    else:
        return config.NORMAL_MULTIPLIER


# =============================================================================
# 统一司机访问API - 消除普通司机(dict)和LLM司机(object)的访问差异
# =============================================================================

def _get_driver_data(driver):
    """获取司机数据（兼容普通司机和LLM司机）"""
    return driver if isinstance(driver, dict) else driver.driver

# 统一司机访问API模块
class DriverAPI:
    @staticmethod
    def is_llm(driver):
        return not isinstance(driver, dict)
    
    @staticmethod
    def x(driver):
        return _get_driver_data(driver)['x']
    
    @staticmethod
    def y(driver):
        return _get_driver_data(driver)['y']
    
    @staticmethod
    def status(driver):
        return _get_driver_data(driver)['status']
    
    @staticmethod
    def revenue(driver):
        return _get_driver_data(driver)['revenue']
    
    @staticmethod
    def distance(driver):
        return _get_driver_data(driver)['total_distance']
    
    @staticmethod
    def driver_id(driver):
        return _get_driver_data(driver)['id']
    
    @staticmethod
    def position(driver):
        data = _get_driver_data(driver)
        return (data['x'], data['y'])
    
    @staticmethod
    def current_order(driver):
        return _get_driver_data(driver)['current_order']
    
    @staticmethod
    def set_status(driver, new_status):
        _get_driver_data(driver)['status'] = new_status
    
    @staticmethod
    def set_current_order(driver, order_id):
        _get_driver_data(driver)['current_order'] = order_id
    
    @staticmethod
    def get_driver_dict(driver):
        return _get_driver_data(driver)

driver = DriverAPI()
