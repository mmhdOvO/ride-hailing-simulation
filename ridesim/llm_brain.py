"""
llm_brain.py
DeepSeek大模型调用模块 - 司机的AI大脑
"""
import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from . import config

# 优先加载仓库根目录 .env（本包位于 ridesim/ 下）
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

class DriverBrain:
    """司机的大脑 - 负责LLM决策"""
    
    def __init__(self, driver_id):
        """
        初始化一个司机的大脑
        driver_id: 司机ID，用于日志区分
        """
        self.driver_id = driver_id
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        # 检查API密钥
        if not self.api_key:
            raise ValueError("❌ 未找到DEEPSEEK_API_KEY，请在.env文件中设置")
        
        # 创建OpenAI客户端（DeepSeek兼容OpenAI SDK）
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=f"{self.base_url}/v1",
        )
        
        # 统计信息
        self.total_calls = 0
        self.total_tokens = 0
        self.total_cost = 0  # 可以估算成本
        self.total_retries = 0
        
        # 决策缓存：key 为观察哈希，value 为动作字母
        # 作用是避免“完全同态观察”下重复请求模型。
        self.decision_cache = {}
        
        if config.DEBUG:
            print(f"  司机{driver_id}的大脑已初始化，使用模型: {self.model}")
    
    def _get_observation_hash(self, observation):
        """
        计算观察哈希（用于缓存）。

        仅使用决策敏感字段，避免把无关噪声写入 cache key。
        """
        # 提取关键信息用于哈希计算
        key_data = {
            'position': observation.get('position'),
            'status': observation.get('status'),
            'time': observation.get('time'),
            'nearby_orders': [(o.get('id'), o.get('start_x'), o.get('start_y'), o.get('fare')) 
                             for o in observation.get('nearby_orders', [])[:5]]
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def build_prompt(self, observation):
        """
        构建结构化 Prompt。
        observation: 包含司机当前观察到的所有信息
        """
        # 提取观察数据
        time_step = observation.get('time', 0)
        position = observation.get('position', (0, 0))
        income = observation.get('income', 0)
        status = observation.get('status', 'idle')
        nearby_orders = observation.get('nearby_orders', [])
        other_drivers = observation.get('other_drivers', [])
        
        # 计算当前时段信息
        ratio = time_step / config.SIMULATION_STEPS if config.SIMULATION_STEPS > 0 else 0
        is_morning_peak = config.USE_TIME_PERIODS and (config.MORNING_PEAK_START <= ratio < config.MORNING_PEAK_END)
        is_evening_peak = config.USE_TIME_PERIODS and (config.EVENING_PEAK_START <= ratio < config.EVENING_PEAK_END)
        is_peak = is_morning_peak or is_evening_peak
        
        # 判断当前位置是否在居民区或工作区
        in_residential = False
        in_work = False
        if config.USE_ZONES:
            # 居民区（左上）
            dx_r = position[0] - config.RESIDENTIAL_CENTER_X
            dy_r = position[1] - config.RESIDENTIAL_CENTER_Y
            in_residential = (dx_r * dx_r + dy_r * dy_r) <= (config.RESIDENTIAL_RADIUS * config.RESIDENTIAL_RADIUS)
            # 工作区（右下）
            dx_w = position[0] - config.WORK_AREA_CENTER_X
            dy_w = position[1] - config.WORK_AREA_CENTER_Y
            in_work = (dx_w * dx_w + dy_w * dy_w) <= (config.WORK_AREA_RADIUS * config.WORK_AREA_RADIUS)
        
        # 时段信息
        if is_peak:
            time_period = "高峰时段" + ("(早高峰-居民区出发多)" if is_morning_peak else "(晚高峰-工作区出发多)")
        else:
            time_period = "平峰时段"
        
        # 格式化附近订单信息（按价值排序，优先展示高价值订单）
        orders_text = ""
        if nearby_orders:
            sorted_orders = []
            for order in nearby_orders:
                dist = order.get('pickup_dist')
                if dist is None:
                    dist = abs(order['start_x'] - position[0]) + abs(order['start_y'] - position[1])
                efficiency = order.get('efficiency')
                if efficiency is None:
                    fare = order.get('fare', 0)
                    efficiency = fare / max(dist, 1)
                sorted_orders.append((order, dist, efficiency))
            
            sorted_orders.sort(key=lambda x: x[2], reverse=True)
            
            for i, (order, dist, eff) in enumerate(sorted_orders[:5]):
                orders_text += f"""
订单{i+1}:
  ID: {order['id']}
  起点: ({order['start_x']}, {order['start_y']}) - 距离你{dist}格
  终点: ({order['end_x']}, {order['end_y']}) - 订单距离{order.get('distance', '?')}格
  收入: {order.get('fare', 0)}元 (每格效率: {eff:.1f}元/格)
  区域前瞻分: {order.get('zone_score', 0):.2f} | 后续潜力分: {order.get('followup_score', 0):.2f}
  已等待: {order.get('waiting_steps', 0)}步
"""
        else:
            orders_text = "  当前附近没有订单，请移动探索或原地等待"
        
        # 其他空闲司机位置（用于避免竞争）
        drivers_text = ""
        if other_drivers:
            drivers_text = "【其他空闲司机位置】（他们也可能来抢订单，请避开他们附近的订单）\n"
            for d in other_drivers[:5]:
                drivers_text += f"  司机{d['id']}: 位于({d['position'][0]}, {d['position'][1]})\n"
        
        # 构建完整 Prompt：包含地图、时段、候选单、竞争态势与动作空间
        prompt = f"""你是一个经验丰富的网约车司机，正在城市网格中接单。你的唯一目标是最大化总收入。

【地图信息】
- 城市大小: {config.GRID_SIZE}x{config.GRID_SIZE}网格
- 居民区（左上角）: 中心({config.RESIDENTIAL_CENTER_X}, {config.RESIDENTIAL_CENTER_Y})，半径{config.RESIDENTIAL_RADIUS}格
- 工作区（右下角）: 中心({config.WORK_AREA_CENTER_X}, {config.WORK_AREA_CENTER_Y})，半径{config.WORK_AREA_RADIUS}格
- 早高峰：居民区订单多（去工作），晚高峰：工作区订单多（回家）

【当前时段信息】
- 当前时间步: {time_step}/{config.SIMULATION_STEPS}
- 当前时段: {time_period}
- 当前位置: ({position[0]}, {position[1]}) {'【在居民区】' if in_residential else ('【在工作区】' if in_work else '')}

【策略指导原则】
1. 你拥有【全局视野】，可以看到整个城市所有区域的订单
2. 目标不是只看当前一单，而是最大化“未来3-5步累计收益”
3. 先看「每格效率」，再看订单终点是否把你带到下一波热点区域
4. **早高峰策略**：优先考虑终点靠近工作区、起点来自居民区的订单
5. **晚高峰策略**：优先考虑终点靠近居民区、起点来自工作区的订单
6. **注意竞争**：若多个空闲司机离同一订单很近，宁可选次优但更稳能抢到的单
7. 如果附近没有合适订单，主动向下一时段更可能出单的区域移动探索

【当前状态】
- 时间步: {time_step}
- 你的位置: ({position[0]}, {position[1]}) {'在居民区' if in_residential else ('在工作区' if in_work else '')}
- 当前累计收入: {income}元
- 你的状态: {status} (idle=空闲, to_pickup=去接客, on_trip=送客中)

{drivers_text}
【全局视野 - 候选订单列表】（按当前效率排序，仅供参考，最终请综合未来收益判断，最多展示10个）
{orders_text}

【可选动作】
A) 接【综合收益最高】的订单（即时收益 + 终点前瞻 + 竞争规避）
B) 向北移动一格 (Y减1)
C) 向南移动一格 (Y加1)
D) 向东移动一格 (X加1)
E) 向西移动一格 (X减1)
F) 原地等待（不推荐，除非有明确理由）

请选择最佳动作。**只回复一个字母**（A、B、C、D、E或F），不要解释，不要输出其他任何内容。
"""
        return prompt
    
    def decide(self, observation):
        """
        根据观察做出决策（带缓存与重试）。
        返回: 动作字母 (A-F)
        """
        if config.DEBUG:
            print(f"  司机{self.driver_id}正在思考决策...")
        
        # 检查缓存
        if config.CACHE_LLM_DECISIONS:
            cache_key = self._get_observation_hash(observation)
            if cache_key in self.decision_cache:
                if config.DEBUG:
                    print(f"  司机{self.driver_id}使用缓存的决策")
                return self.decision_cache[cache_key]
        
        # 构建Prompt
        prompt = self.build_prompt(observation)
        
        # 重试机制
        max_retries = config.MAX_API_RETRIES
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # 调用DeepSeek API
                start_time = time.time()
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的网约车司机，只输出单个字母决策，不要解释。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=10,
                    timeout=config.API_TIMEOUT,
                )
                
                elapsed = time.time() - start_time
                
                # 提取决策
                decision = response.choices[0].message.content.strip().upper()
                
                # 输出约束清理：模型可能返回多余文本，这里只取首个合法动作
                if decision and decision[0] in ['A','B','C','D','E','F']:
                    final_decision = decision[0]
                else:
                    # 默认动作：原地等待
                    final_decision = 'F'
                    if config.DEBUG:
                        print(f"  司机{self.driver_id}收到异常响应: '{decision}'，使用默认动作F")
                
                # 统计信息
                self.total_calls += 1
                if hasattr(response, 'usage'):
                    self.total_tokens += response.usage.total_tokens
                
                if config.DEBUG:
                    print(f"  司机{self.driver_id}决策: {final_decision} (耗时: {elapsed:.2f}秒)")
                
                # 缓存决策
                if config.CACHE_LLM_DECISIONS:
                    self.decision_cache[cache_key] = final_decision
                
                return final_decision
                
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"  司机{self.driver_id}调用API失败: {e}，已达到最大重试次数")
                    return 'F'
                else:
                    self.total_retries += 1
                    print(f"  司机{self.driver_id}调用API失败: {e}，正在重试 ({retry_count}/{max_retries})...")
                    time.sleep(1)
        return 'F'
    
    def get_stats(self):
        """获取大脑统计信息"""
        return {
            'calls': self.total_calls,
            'tokens': self.total_tokens,
            'estimated_cost': self.total_tokens * 0.000001,
            'retries': self.total_retries,
            'cache_hits': len(self.decision_cache)
        }


if __name__ == "__main__":
    print("测试LLM大脑模块...")
    brain = DriverBrain(driver_id=999)
    test_observation = {
        'time': 42,
        'position': (5, 5),
        'income': 120,
        'status': 'idle',
        'nearby_orders': [
            {'id': 1, 'start_x': 3, 'start_y': 3, 'end_x': 8, 'end_y': 8, 'fare': 30, 'waiting_steps': 2},
            {'id': 2, 'start_x': 7, 'start_y': 6, 'end_x': 2, 'end_y': 1, 'fare': 25, 'waiting_steps': 1}
        ]
    }
    decision = brain.decide(test_observation)
    print(f"测试决策结果: {decision}")
    decision_from_cache = brain.decide(test_observation)
    print(f"缓存决策结果: {decision_from_cache}")
    print(f"统计信息: {brain.get_stats()}")
