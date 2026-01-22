"""
main_interactive.py
交互式仿真控制台
提供单步执行、自动运行、修改参数等功能
"""
import sys
import time
from simulation import Simulation
from config import SIMULATION_STEPS, VISUALIZE, STEP_DELAY

def print_menu():
    """打印交互菜单"""
    print("\n" + "="*50)
    print("请选择操作指令:")
    print("  [回车] 或 [s] : 执行一个时间步 (Step)")
    print("  [a]          : 自动运行剩余所有步 (Auto run)")
    print("  [f]          : 快速无延迟自动运行 (Fast run)")
    print("  [c]          : 查看当前配置 (Config)")
    print("  [p]          : 打印当前详细状态 (Print state)")
    print("  [q]          : 退出仿真 (Quit)")
    print("="*50)

def main_interactive():
    """交互式主函数"""
    print("\n🚗 网约车仿真系统 - 交互式控制模式")
    print("="*50)

    # 创建仿真实例
    sim = Simulation()
    print(f"目标总步数: {SIMULATION_STEPS}")

    while sim.is_running:
        print_menu()
        # 等待用户输入
        cmd = input(f"当前步: [{sim.current_step:3d}/{SIMULATION_STEPS}] 请输入指令: ").strip().lower()

        if cmd in ('', 's', 'step'):  # 单步执行
            print(f"\n>>> 正在执行第 {sim.current_step} 步...")
            if not sim.step():  # 如果 step() 返回 False，表示仿真结束
                break
            # 单步执行后，如果需要可视化，可以暂停一下以便观察
            if VISUALIZE:
                # 这里设置一个比自动模式稍长的暂停，方便你看清楚
                input("  单步完成！请查看可视化窗口，按回车继续...")

        elif cmd == 'a':  # 自动运行（保留可视化延迟）
            sim.auto_run()
            break  # 自动运行结束后，退出菜单循环

        elif cmd == 'f':  # 快速运行（无延迟，用于快速获得结果）
            print("快速自动运行中... (关闭了可视化延迟)")
            original_delay = STEP_DELAY
            # 临时修改配置：关闭可视化延迟
            import config
            config.STEP_DELAY = 0.0
            sim.auto_run()
            config.STEP_DELAY = original_delay  # 恢复设置
            break

        elif cmd == 'c':  # 查看配置
            print("\n当前核心配置:")
            print(f"  网格大小: {sim.drivers[0]['x'] if sim.drivers else 'N/A'}x{sim.drivers[0]['y'] if sim.drivers else 'N/A'}")
            print(f"  司机数量: {len(sim.drivers)}")
            print(f"  总目标步数: {SIMULATION_STEPS}")
            print(f"  当前订单数: {len(sim.orders)}")
            idle = sum(1 for d in sim.drivers if d['status'] == 'idle')
            print(f"  空闲司机数: {idle}")

        elif cmd == 'p':  # 打印状态
            from utils import print_grid
            print(f"\n=== 第 {sim.current_step} 步详细状态 ===")
            # 调用仿真类内部的打印方法，或者直接打印关键数据
            if hasattr(sim, '_print_step_status'):
                sim._print_step_status()
            else:
                print(" (详细状态打印功能未启用) ")
            # 打印文本网格
            print_grid(sim.drivers, sim.orders)

        elif cmd == 'q':  # 退出
            print("退出交互式仿真。")
            sim.is_running = False
            break

        else:
            print(f"未知指令: '{cmd}'，请参考菜单输入。")

    # 仿真结束后的处理
    if not sim.is_running:
        print("\n仿真已终止。")
    # 保持可视化窗口
    if VISUALIZE and sim.current_step > 0:
        print("关闭图形窗口以完全退出程序...")
        import matplotlib.pyplot as plt
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main_interactive()