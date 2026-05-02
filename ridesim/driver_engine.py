"""
driver_engine.py
司机移动与状态更新引擎
"""
import random

from . import config
from .utils import get_road_neighbors, next_step_on_road, shortest_road_distance, snap_to_road


# ========== 普通司机更新函数（字典类型） ==========
def update_rule_based_driver(driver, orders, current_step=0):
    """
    更新普通规则司机（字典类型）。

    该路径只处理“非空闲状态推进”（to_pickup/on_trip）。
    空闲司机在 simulation + dispatcher 阶段完成选单与状态切换。
    """
    # 查找当前订单
    target_order = next((o for o in orders if o['id'] == driver['current_order']), None)
    if not target_order:
        driver['status'] = 'idle'
        driver['current_order'] = None
        return

    if driver['status'] == 'to_pickup':
        arrived = move_driver_towards(driver, target_order['start_x'], target_order['start_y'], current_step)
        if arrived:
            driver['status'] = 'on_trip'
            if config.DEBUG:
                print(f"  司机{driver['id']}已接到订单{target_order['id']}")

    elif driver['status'] == 'on_trip':
        arrived = move_driver_towards(driver, target_order['end_x'], target_order['end_y'], current_step)
        if arrived:
            target_order['status'] = 'completed'
            driver['revenue'] += target_order['fare']
            driver['status'] = 'idle'
            driver['current_order'] = None
            if config.DEBUG:
                print(f"  司机{driver['id']}完成订单{target_order['id']}，收入+{target_order['fare']}元")

def move_driver_towards(driver, target_x, target_y, current_step=0):
    """
    让司机向目标坐标移动一格（曼哈顿距离）。
    返回 True 如果司机已经到达目标，否则返回 False。
    """
    driver['x'], driver['y'] = snap_to_road(driver['x'], driver['y'])
    tx, ty = snap_to_road(target_x, target_y)
    # 记录移动前的位置
    driver['history'].append((driver['x'], driver['y']))

    # 如果已在目标点，无需移动
    if driver['x'] == tx and driver['y'] == ty:
        return True

    nxt = next_step_on_road(driver['x'], driver['y'], tx, ty)
    if nxt is None:
        return False
    nx, ny = nxt
    if (nx, ny) == (driver['x'], driver['y']):
        return driver['x'] == tx and driver['y'] == ty

    driver['x'], driver['y'] = nx, ny

    driver['total_distance'] += 1
    return driver['x'] == tx and driver['y'] == ty

def update_driver(driver_obj, all_orders, current_step=None):
    """
    更新司机状态（兼容普通司机字典和LLMDriver对象）
    """
    # 统一入口：对外不暴露“普通司机/LLM司机”的类型分叉
    if isinstance(driver_obj, dict):
        update_rule_based_driver(driver_obj, all_orders)
    else:
        driver_obj.update(all_orders, current_step)

class LLMDriver:
    """
    LLM驱动的司机 - 拥有自己的AI大脑
    与普通司机数据结构兼容，但决策由大模型做出
    """
    
    def __init__(self, driver_id):
        """初始化LLM司机"""
        from .llm_brain import DriverBrain
        
        x, y = snap_to_road(random.randint(0, config.GRID_SIZE - 1), random.randint(0, config.GRID_SIZE - 1))
        self.driver = {
            'id': driver_id,
            'x': x,
            'y': y,
            'status': 'idle',
            'current_order': None,
            'revenue': 0,
            'total_distance': 0,
            'history': []
        }
        
        self.brain = DriverBrain(driver_id)
        self.decision_history = []
    
    def get_driver_dict(self):
        """返回与普通司机兼容的字典格式"""
        return self.driver


    def _get_visible_waiting_orders(self, all_orders):
        """
        获取当前司机可见范围内的等待订单。

        当前等价全局视野（visible_range = GRID_SIZE * 2），
        但保留该函数作为未来“局部视野实验”的单一入口。
        """
        visible_range = config.GRID_SIZE * 2
        driver = self.driver
        return [
            o for o in all_orders
            if o['status'] == 'waiting'
            and o.get('ready_for_dispatch', True)
            and abs(o['start_x'] - driver['x']) + abs(o['start_y'] - driver['y']) <= visible_range
        ]
    
    def observe(self, all_orders, current_step, all_drivers=None):
        """
        组装给 LLM 的观察信息。

        说明：
        - 在这一层预计算 pickup_dist / efficiency 等特征，
          避免下游重复算曼哈顿距离；
        - nearby_orders 已按即时效率预排序，供 prompt 展示与候选过滤。
        """
        nearby = []
        px, py = self.driver['x'], self.driver['y']
        for order in self._get_visible_waiting_orders(all_orders):
            pickup_dist = abs(order['start_x'] - px) + abs(order['start_y'] - py)
            road_pickup_dist = shortest_road_distance(px, py, order['start_x'], order['start_y'])
            effective_dist = road_pickup_dist if road_pickup_dist is not None else pickup_dist
            zone_score = self._zone_score(order['end_x'], order['end_y'], current_step)
            followup_score = self._expected_followup_score(order, current_step)
            nearby.append({
                **order,
                'pickup_dist': pickup_dist,
                'road_pickup_dist': road_pickup_dist,
                'efficiency': order['fare'] / max(effective_dist, 1),
                'zone_score': zone_score,
                'followup_score': followup_score,
            })

        nearby.sort(
            key=lambda o: (
                -o['efficiency'],
                o['road_pickup_dist'] if o.get('road_pickup_dist') is not None else 10**9,
                o['pickup_dist'],
            )
        )
        
        other_driver_info = []
        if all_drivers:
            for d in all_drivers:
                if d['id'] != self.driver['id'] and d['status'] == 'idle':
                    other_driver_info.append({
                        'id': d['id'],
                        'position': (d['x'], d['y']),
                        'status': d['status']
                    })
        
        neighbors = get_road_neighbors(px, py)
        direction_map = {(0, -1): 'B', (0, 1): 'C', (1, 0): 'D', (-1, 0): 'E'}
        road_available_moves = []
        for nx, ny in neighbors:
            dx, dy = nx - px, ny - py
            mv = direction_map.get((dx, dy))
            if mv:
                road_available_moves.append(mv)

        observation = {
            'time': current_step,
            'position': (px, py),
            'income': self.driver['revenue'],
            'status': self.driver['status'],
            'nearby_orders': nearby[:10],
            'other_drivers': other_driver_info,
            'road_available_moves': sorted(set(road_available_moves)),
        }
        
        return observation
    
    def make_decision(self, all_orders, current_step, all_drivers=None):
        """向大模型请求动作决策并记录决策日志；返回动作字符串 (A-F)。"""
        observation = self.observe(all_orders, current_step, all_drivers)
        decision = self.brain.decide(observation)
        self.decision_history.append({
            'step': current_step,
            'observation': observation,
            'decision': decision
        })
        return decision
    
    def move(self, direction):
        """根据方向移动一格：'B'(北), 'C'(南), 'D'(东), 'E'(西)"""
        self.driver['x'], self.driver['y'] = snap_to_road(self.driver['x'], self.driver['y'])
        old_x, old_y = self.driver['x'], self.driver['y']

        preferred = {
            'B': (0, -1),
            'C': (0, 1),
            'D': (1, 0),
            'E': (-1, 0),
        }.get(direction, (0, 0))

        neighbors = get_road_neighbors(old_x, old_y)
        if not neighbors:
            return False

        tx, ty = old_x + preferred[0], old_y + preferred[1]
        # 优先选“接近期望方向”的道路邻居
        nx, ny = min(neighbors, key=lambda p: abs(p[0] - tx) + abs(p[1] - ty))
        if (nx, ny) == (old_x, old_y):
            return False

        self.driver['x'], self.driver['y'] = nx, ny
        self.driver['history'].append((old_x, old_y))
        self.driver['total_distance'] += 1
        return True

    def _zone_score(self, x, y, current_step):
        """
        给目标点一个时段前瞻分（启发式）：
        - 早高峰更偏居民区
        - 晚高峰更偏工作区
        - 平峰给小幅中性分
        """
        if config.SIMULATION_STEPS <= 0:
            return 0.0
        ratio = current_step / config.SIMULATION_STEPS
        in_residential = (x - config.RESIDENTIAL_CENTER_X) ** 2 + (y - config.RESIDENTIAL_CENTER_Y) ** 2 <= config.RESIDENTIAL_RADIUS ** 2
        in_work = (x - config.WORK_AREA_CENTER_X) ** 2 + (y - config.WORK_AREA_CENTER_Y) ** 2 <= config.WORK_AREA_RADIUS ** 2

        if config.USE_TIME_PERIODS and config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END:
            return 1.0 if in_residential else (0.3 if in_work else 0.6)
        if config.USE_TIME_PERIODS and config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END:
            return 1.0 if in_work else (0.3 if in_residential else 0.6)
        return 0.6 if (in_residential or in_work) else 0.4

    def _competition_penalty(self, order, all_drivers):
        """估计竞争惩罚：离该订单近的空闲司机越多，分值扣减越大。"""
        if not all_drivers:
            return 0.0
        ox, oy = order['start_x'], order['start_y']
        competitors = 0
        for d in all_drivers:
            if d['id'] == self.driver['id'] or d['status'] != 'idle':
                continue
            dist = abs(d['x'] - ox) + abs(d['y'] - oy)
            if dist <= 4:
                competitors += 1
        return min(0.8, competitors * 0.15)

    def _expected_followup_score(self, order, current_step):
        """
        估计“做完这一单后接下一单”的潜力（中期收益）：
        - 终点越靠近下一时段热点，得分越高
        - 终点到目标热点的重定位成本越低，得分越高
        """
        ratio = current_step / max(1, config.SIMULATION_STEPS)
        if config.USE_TIME_PERIODS and config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END:
            tx, ty = config.WORK_AREA_CENTER_X, config.WORK_AREA_CENTER_Y
        elif config.USE_TIME_PERIODS and config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END:
            tx, ty = config.RESIDENTIAL_CENTER_X, config.RESIDENTIAL_CENTER_Y
        else:
            tx, ty = config.GRID_SIZE // 2, config.GRID_SIZE // 2

        relocation_dist = abs(order['end_x'] - tx) + abs(order['end_y'] - ty)
        return max(0.0, 1.0 - relocation_dist / max(config.GRID_SIZE, 1))

    def _order_long_term_score(self, order, current_step, all_drivers):
        """
        长期收益评分（当前 LLM 选单的核心打分函数）：
        - 即时效率（收入 / 接驾距离）
        - 前瞻区域分（看订单终点落到哪）
        - 后续接单潜力（终点到下一波热点的成本）
        - 竞争惩罚（热点高竞争单降权）
        """
        dx = abs(order['start_x'] - self.driver['x']) + abs(order['start_y'] - self.driver['y'])
        immediate_eff = order['fare'] / max(dx, 1)
        zone_bonus = self._zone_score(order['end_x'], order['end_y'], current_step)
        followup_bonus = self._expected_followup_score(order, current_step)
        competition_penalty = self._competition_penalty(order, all_drivers)

        # 收益优先权重：即时收益主导 + 中期机会价值
        return (
            immediate_eff * 0.55
            + zone_bonus * 0.20
            + followup_bonus * 0.25
            - competition_penalty
        )

    def decide_only(self, all_orders, current_step, all_drivers=None):
        """
        仅决策不执行（供公平分配阶段使用）。

        返回：
        - decision: A-F
        - selected_order: 若 decision 为 A，则返回候选订单对象
        """
        nearby_orders = self._get_visible_waiting_orders(all_orders)
        
        if not nearby_orders:
            return ('F', None)
        
        decision = self.make_decision(all_orders, current_step, all_drivers)
        
        if decision == 'A' and nearby_orders:
            best_order = max(
                nearby_orders,
                key=lambda order: self._order_long_term_score(order, current_step, all_drivers),
            )
            return ('A', best_order)
        return (decision, None)

    def execute_decision(self, decision, selected_order):
        """
        执行决策并尝试锁单。

        关键保护：
        - 仅当订单仍为 waiting 时允许锁定，
          防止冲突分配后重复抢单导致状态错乱。
        """
        driver = self.driver
        
        if decision == 'A' and selected_order and selected_order.get('status') == 'waiting':
            driver['status'] = 'to_pickup'
            driver['current_order'] = selected_order['id']
            selected_order['status'] = 'to_pickup'
            if config.DEBUG:
                dist = abs(selected_order['start_x'] - driver['x']) + abs(selected_order['start_y'] - driver['y'])
                print(f"  LLM司机{driver['id']}决定接订单{selected_order['id']}（效率{selected_order['fare']/max(dist,1):.1f}元/格）")
        elif decision in ['B','C','D','E']:
            self.move(decision)
        else:
            driver['history'].append((driver['x'], driver['y']))

    def update(self, all_orders, current_step):
        """
        每步更新 LLM 司机状态。

        该路径只服务“非空闲状态推进”（to_pickup/on_trip）；
        空闲司机的决策与接单由 simulation + dispatcher + execute_decision 统一负责。
        """
        driver = self.driver

        if driver['status'] == 'to_pickup':
            target_order = next((o for o in all_orders if o['id'] == driver['current_order']), None)
            if not target_order:
                driver['status'] = 'idle'
                return
            arrived = move_driver_towards(driver, target_order['start_x'], target_order['start_y'], current_step)
            if arrived:
                driver['status'] = 'on_trip'
                if config.DEBUG:
                    print(f"  LLM司机{driver['id']}已接到订单{target_order['id']}")
        
        elif driver['status'] == 'on_trip':
            target_order = next((o for o in all_orders if o['id'] == driver['current_order']), None)
            if not target_order:
                driver['status'] = 'idle'
                return
            arrived = move_driver_towards(driver, target_order['end_x'], target_order['end_y'], current_step)
            if arrived:
                target_order['status'] = 'completed'
                driver['revenue'] += target_order['fare']
                driver['status'] = 'idle'
                driver['current_order'] = None
                if config.DEBUG:
                    print(f"  LLM司机{driver['id']}完成订单{target_order['id']}，收入+{target_order['fare']}元")
