"""
config.py
仿真系统参数配置中心
所有核心参数都在这里调整
"""

# 使用建议：
# - 做可复现实验时固定 RANDOM_SEED；
# - 调试逻辑时可开 DEBUG + 关 VISUALIZE；
# - 批量跑实验时建议关 VISUALIZE 以提升速度。

# ===== 仿真核心参数 =====
GRID_SIZE = 30           # 城市网格大小 (N x N)
NUM_DRIVERS = 20         # 司机总数
SIMULATION_STEPS = 200   # 仿真运行的总时间步数
ORDER_PROBABILITY = 0.3  # 每个时间步、每个格子生成一个新订单的概率

# ===== 时段模拟 =====
USE_TIME_PERIODS = True  # 是否启用时段模拟
# 时间划分：9份
# 第1份：正常时段
# 第2份：早高峰
# 第3-6份：正常时段
# 第7-8份：晚高峰
# 第9份：正常时段
MORNING_PEAK_START = 1/9      # 早高峰开始步数 (占SIMULATION_STEPS的比例, 0-1)
MORNING_PEAK_END = 2/9     # 早高峰结束步数
EVENING_PEAK_START = 6/9   # 晚高峰开始步数
EVENING_PEAK_END = 8/9     # 晚高峰结束步数
MORNING_PEAK_MULTIPLIER = 1.8  # 早高峰订单倍数
EVENING_PEAK_MULTIPLIER = 1.6  # 晚高峰订单倍数
NORMAL_MULTIPLIER = 1.0    # 平峰期订单倍数

# ===== 区域模拟 =====
USE_ZONES = True          # 是否启用区域划分
AUTO_SCALE_ZONES = True   # 是否按 GRID_SIZE 自动缩放居民区/工作区参数

# 区域缩放模板（基于旧版 30x30 地图参数）
_BASE_GRID_SIZE = 30
_RES_CENTER_RATIO = 8 / _BASE_GRID_SIZE
_WORK_CENTER_RATIO = 22 / _BASE_GRID_SIZE
_ZONE_RADIUS_RATIO = 12 / _BASE_GRID_SIZE

# 居民区（左上角）与工作区（右下角）默认值，会在 auto_scale_zone_params 中按 GRID_SIZE 重算
RESIDENTIAL_CENTER_X = 8
RESIDENTIAL_CENTER_Y = 8
RESIDENTIAL_RADIUS = 12
WORK_AREA_CENTER_X = 22
WORK_AREA_CENTER_Y = 22
WORK_AREA_RADIUS = 12


def auto_scale_zone_params():
    """
    按当前 GRID_SIZE 自动重算居民区/工作区范围参数。

    规则：
    - 圆心位置按比例缩放
    - 半径按比例缩放，并限制在 [2, GRID_SIZE//2] 之间
    """
    global RESIDENTIAL_CENTER_X, RESIDENTIAL_CENTER_Y, RESIDENTIAL_RADIUS
    global WORK_AREA_CENTER_X, WORK_AREA_CENTER_Y, WORK_AREA_RADIUS

    if GRID_SIZE <= 0:
        return

    res_center = int(round(_RES_CENTER_RATIO * GRID_SIZE))
    work_center = int(round(_WORK_CENTER_RATIO * GRID_SIZE))
    radius = int(round(_ZONE_RADIUS_RATIO * GRID_SIZE))
    radius = max(2, min(radius, max(2, GRID_SIZE // 2)))

    edge_limit = max(0, GRID_SIZE - 1)
    RESIDENTIAL_CENTER_X = max(0, min(edge_limit, res_center))
    RESIDENTIAL_CENTER_Y = max(0, min(edge_limit, res_center))
    WORK_AREA_CENTER_X = max(0, min(edge_limit, work_center))
    WORK_AREA_CENTER_Y = max(0, min(edge_limit, work_center))
    RESIDENTIAL_RADIUS = radius
    WORK_AREA_RADIUS = radius


if AUTO_SCALE_ZONES:
    auto_scale_zone_params()

# ===== 调度算法配置 =====
# NORMAL_STRATEGY 仅作用于“普通司机”选单行为，LLM司机由其策略评分+模型决策决定。
NORMAL_STRATEGY = 'nearest'  # 普通司机选单策略: 'nearest'(最近), 'random'(随机), 'round_robin'(轮询)
FORCE_ONE_STEP_BEFORE_DISPATCH = True  # 新订单出现后强制等待一步，下一步才可被抢单
DEBUG = True             # 是否打印调试信息（如调度详情）
RANDOM_SEED = 14         # 随机种子。固定此值可使每次运行结果相同，便于调试

# ===== 可视化参数 =====
VISUALIZE = True        # 是否开启图形化界面
STEP_DELAY = 0.3         # 可视化时，每个时间步暂停的秒数（调小可加速）
PLOT_DRIVER_NUM = True   # 是否在可视化中显示司机编号
DISTINGUISH_LLM_IN_VIZ = True  # 可视化中是否区分LLM司机与普通司机

# ===== LLM相关配置 =====
USE_LLM_DRIVERS = True           # 是否使用LLM司机（调试时先关闭）
NUM_LLM_DRIVERS = 10                # LLM司机数量（如果USE_LLM_DRIVERS=True）

# ===== API调用控制 =====
API_TIMEOUT = 10                    # API调用超时（秒）
MAX_API_RETRIES = 2                  # API调用失败重试次数
CACHE_LLM_DECISIONS = True           # 是否缓存决策结果（节省成本）
