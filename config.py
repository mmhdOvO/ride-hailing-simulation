"""
config.py
仿真系统参数配置中心
所有核心参数都在这里调整
"""

# ===== 仿真核心参数 =====
GRID_SIZE = 10           # 城市网格大小 (N x N)
NUM_DRIVERS = 10         # 司机总数
SIMULATION_STEPS = 100   # 仿真运行的总时间步数
ORDER_PROBABILITY = 0.2  # 每个时间步、每个格子生成一个新订单的概率

# ===== 可视化参数 =====
VISUALIZE = True         # 是否开启图形化界面
STEP_DELAY = 0.3         # 可视化时，每个时间步暂停的秒数（调小可加速）
PLOT_DRIVER_NUM = True   # 是否在可视化中显示司机编号

# ===== 系统与调试参数 =====
DEBUG = True             # 是否打印调试信息（如调度详情）
RANDOM_SEED = 42         # 随机种子。固定此值可使每次运行结果相同，便于调试