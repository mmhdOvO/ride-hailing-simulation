# debug_test.py
from config import *
ORDER_PROBABILITY = 1.0  # 调到最大，确保每一步都生成订单
NUM_DRIVERS = 1          # 只留一个司机，减少干扰
SIMULATION_STEPS = 5
DEBUG = True
VISUALIZE = True

print("=== 开始最小化调试 ===")
from simulation import Simulation
sim = Simulation()
# 手动运行几步
for i in range(3):
    print(f"\n--- 强制手动执行第 {i} 步 ---")
    sim.step()
    input("按回车继续下一步...")