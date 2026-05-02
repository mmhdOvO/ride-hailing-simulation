# 网约车动态调度仿真（含 LLM 司机）

离散时间网格城市中的订单生成、司机移动与调度仿真。支持**普通司机（启发式选单）**与 **LLM 司机（DeepSeek API 决策）**混合车队，并提供完成率、等待时间、收入与 Gini 等统计，便于与传统策略对比实验。

## 环境要求

- Python **3.10+**（开发验证常用 3.12）
- Windows / macOS / Linux 均可；可视化默认使用 `TkAgg`，无图形环境时请关闭 `config.VISUALIZE`

## 安装

```bash
cd ride-sharing-sim
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
# source venv/bin/activate

pip install -r requirements.txt
```

启用 LLM 司机时，需在项目根目录创建 `.env`（可参考下方变量名）：

```env
DEEPSEEK_API_KEY=你的密钥
# 可选（base_url 不变，与官方 OpenAI 兼容接口一致）
DEEPSEEK_BASE_URL=https://api.deepseek.com
# 模型分工（默认）：司机选单 = Flash，仿真分析报告 = Pro（base_url 不变，仅改 model 名）
DEEPSEEK_MODEL_DRIVER=deepseek-v4-flash
DEEPSEEK_MODEL_ANALYSIS=deepseek-v4-pro
# 未单独设置 DRIVER / ANALYSIS 时，会回退到旧变量 DEEPSEEK_MODEL（司机端与报告端均可用其兜底）
# DEEPSEEK_MODEL=deepseek-chat
```

不使用 LLM 时，在 `ridesim/config.py` 中设置 `USE_LLM_DRIVERS = False` 即可，无需配置 API。

## 快速运行

| 方式 | 命令 | 说明 |
|------|------|------|
| 交互式单步/自动跑 | `python main.py` | 菜单驱动，可选可视化暂停 |
| Web 演示（乘客/司机/控制台） | `streamlit run web_app.py` | 浏览器内下单、看司机状态与地图快照 |
| 非交互一整次仿真 | 在代码中 `Simulation().run()` | 适合批量实验 |

**建议**：批量测试时在脚本里设 `config.VISUALIZE = False`、`config.DEBUG = False`，避免弹窗与刷屏。

## 配置说明（`ridesim/config.py`）

- **网格与步数**：`GRID_SIZE`、`SIMULATION_STEPS`、`NUM_DRIVERS`
- **订单强度**：`ORDER_PROBABILITY`，以及 `USE_TIME_PERIODS` / 高峰倍率
- **区域 OD**：`USE_ZONES` 及居民区/工作区圆心与半径
- **传统选单策略**（普通司机在抢单模式下）：`NORMAL_STRATEGY`，可选 `nearest`、`random`、`round_robin`
- **LLM**：`USE_LLM_DRIVERS`、`NUM_LLM_DRIVERS`；API 相关见 `ridesim/llm_brain.py` 与 `API_TIMEOUT`、`CACHE_LLM_DECISIONS` 等

## 项目结构

```
ridesim/                 # 仿真核心包（业务代码集中在此）
  __init__.py            # 导出 Simulation
  config.py              # 全局参数
  utils.py               # 订单生成、距离、司机统一访问 API
  simulation.py          # 主循环、统计与导出
  dispatcher.py          # 公平调度、冲突消解、启发式选单
  driver_engine.py       # 普通司机更新、LLMDriver
  llm_brain.py           # DeepSeek（OpenAI 兼容）调用与 Prompt
  visualizer.py          # Matplotlib 动态网格
main.py                  # 交互入口
web_app.py               # Streamlit：乘客端/司机端/仿真控制台
tests/                   # 自动化测试脚本
  health/                # 健康性/回归测试（unittest）
  experiments/           # 论文实验脚本（生成对比 JSON）
tests/output/            # 测试导出 JSON（可加入 .gitignore）
requirements.txt
README.md
.env                     # API 密钥（勿提交仓库）
```

代码中通过 `from ridesim import config`、`from ridesim.simulation import Simulation` 等方式引用；**请在仓库根目录运行** `main.py` 与 `tests/` 下脚本，以便正确加载包与 `.env`。

## 健康性测试（`tests/health`）

在**仓库根目录**执行：

```bash
python -m unittest discover -s tests/health -p "test_*.py" -v
# 或按需单独运行：
python tests/health/test_01_smoke.py                 # 无 LLM 快速冒烟
python tests/health/test_02_dispatch_strategies.py   # 三种普通司机策略可执行性
python tests/health/test_03_export_schema.py         # 导出 JSON 结构校验
python tests/health/test_04_llm_smoke_optional.py    # 可选 LLM 冒烟（需 DEEPSEEK_API_KEY）
python tests/health/test_05_multi_seed_regression.py # 多随机种子稳定性回归
```

## 论文实验脚本（`tests/experiments`）

在**仓库根目录**执行（默认输出到 `tests/output/`）：

```bash
python tests/experiments/exp_01_baseline_strategies.py
python tests/experiments/exp_02_llm_vs_baseline.py --llm-drivers 10
python tests/experiments/exp_03_multi_seed_compare.py --seeds 3 7 11 19 29
python tests/experiments/exp_04_high_load_compare.py --drivers 12 --order-prob 0.45
python tests/experiments/exp_05_report_table.py
```

其中 `exp_05_report_table.py` 会读取 `tests/output/exp_*.json` 并生成论文可粘贴的 Markdown 报告：

```bash
tests/output/experiment_report.md
```

## 统计与导出

- `Simulation.collect_statistics()`：完成率、总流水、总里程、完成单平均/最大等待、收入 Gini 与变异系数等。
- `Simulation.export_data(path)`：写入配置快照、统计数据与终态（司机/订单）。

## 模型假设（写论文/验收时建议写明）

- **抢单模式**：司机（或 LLM）在待接订单池上提交意向，平台侧以 `dispatch_with_conflict_resolution` + `resolve_conflicts` 消解冲突。
- **传统调度**：在本项目中主要指**普通司机的选单启发式**（与 LLM 决策对比），统一在公平抢单框架下完成冲突消解。
- **移动**：曼哈顿网格，每步一格；未建模真实路网车速。

## 许可证

毕业设计/课程项目用途请遵循所在院系对代码与数据的要求；第三方 API 使用须遵守 DeepSeek 等服务条款。
