"""
main.py
程序主入口
从这里启动整个仿真系统
"""
from simulation import Simulation

def main():
    """主函数"""
    print("\n🚗 欢迎使用网约车仿真系统！")
    print("正在启动...\n")

    # 创建仿真实例
    sim = Simulation()

    # 运行仿真
    sim.run()

    print("\n✅ 第一阶段 - 基础仿真已完成！")
    print("接下来你可以：")
    print("  1. 修改 config.py 中的参数（如更多司机、更大网格）重新运行")
    print("  2. 在 dispatcher.py 中添加新的调度算法（如轮流调度）")
    print("  3. 进入第二阶段：集成大语言模型（LLM）决策")

if __name__ == "__main__":
    main()