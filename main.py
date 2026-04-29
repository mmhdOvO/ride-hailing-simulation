"""
main.py
交互式仿真控制台
提供单步执行、自动运行、修改参数等功能
"""
from ridesim import config
from ridesim.simulation import Simulation
from ridesim.utils import driver as drv


def print_cli_menu():
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

def main():
    """
    交互入口。

    该文件只负责“人机交互控制”，
    具体仿真逻辑由 ridesim.simulation.Simulation 执行。
    """
    print("\n网约车仿真系统")
    print("="*50)

    sim = Simulation()
    print(f"目标总步数: {config.SIMULATION_STEPS}")

    while sim.is_running:
        print_cli_menu()
        cmd = input(f"当前步: [{sim.current_step:3d}/{config.SIMULATION_STEPS}] 请输入指令: ").strip().lower()

        if cmd in ('', 's', 'step'):
            # 单步推进：便于课堂演示或人工观察每一步状态变化
            print(f"\n>>> 正在执行第 {sim.current_step} 步...")
            if not sim.step():
                break
            if config.VISUALIZE:
                input("  单步完成！请查看可视化窗口，按回车继续...")

        elif cmd == 'a':
            # 正常自动运行（保留可视化节奏）
            sim.auto_run()
            break

        elif cmd == 'f':
            # 快速模式：临时关闭步间延迟，加速批量实验
            print("快速自动运行中... (关闭了可视化延迟)")
            original_delay = config.STEP_DELAY
            config.STEP_DELAY = 0.0
            sim.auto_run()
            config.STEP_DELAY = original_delay
            break

        elif cmd == 'c':
            print("\n当前核心配置:")
            print(f"  网格大小: {config.GRID_SIZE}x{config.GRID_SIZE}")
            print(f"  司机数量: {len(sim.drivers)}")
            print(f"  总目标步数: {config.SIMULATION_STEPS}")
            print(f"  当前订单数: {len(sim.orders)}")
            idle = sum(1 for d in sim.drivers if drv.status(d) == 'idle')
            print(f"  空闲司机数: {idle}")

        elif cmd == 'p':
            from ridesim.utils import print_grid
            print(f"\n=== 第 {sim.current_step} 步详细状态 ===")
            if hasattr(sim, '_print_step_status'):
                sim._print_step_status()
            else:
                print(" (详细状态打印功能未启用) ")
            print_grid(sim.drivers, sim.orders)

        elif cmd == 'q':
            print("退出交互式仿真。")
            sim.is_running = False
            break

        else:
            print(f"未知指令: '{cmd}'，请参考菜单输入。")

    if not sim.is_running:
        print("\n仿真已终止。")
    if config.VISUALIZE and sim.current_step > 0:
        print("关闭图形窗口以完全退出程序...")
        import matplotlib.pyplot as plt
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()
