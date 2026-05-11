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

启用 LLM 司机时，可在项目根目录复制 **`.env.example` 为 `.env`** 并填写密钥；或直接新建 `.env`，变量名如下：

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
saved_runs/              # 跑满仿真后的 JSON 存档（默认不入库，见 .gitignore）
saved_ai_analyses/       # 大模型分析报告 Markdown（默认不入库）
requirements.txt
README.md
.env                     # API 密钥（勿提交仓库）
```

代码中通过 `from ridesim import config`、`from ridesim.simulation import Simulation` 等方式引用；**请在仓库根目录运行** `main.py` 或 `streamlit run web_app.py`，以便正确加载包与 `.env`。

本仓库**不包含**自动化测试目录 `tests/`；指标对比与存档可使用网页「AI 仿真报告」或自行编写脚本调用 `Simulation`。

## 统计与导出

- `Simulation.collect_statistics()`：完成率、总流水、总里程、完成单平均/最大等待、收入 Gini 与变异系数等。
- `Simulation.export_data(path)`：写入配置快照、统计数据与终态（司机/订单）。

## 模型假设（写论文/验收时建议写明）

- **抢单模式**：司机（或 LLM）在待接订单池上提交意向，平台侧以 `dispatch_with_conflict_resolution` + `resolve_conflicts` 消解冲突。
- **传统调度**：在本项目中主要指**普通司机的选单启发式**（与 LLM 决策对比），统一在公平抢单框架下完成冲突消解。
- **移动**：曼哈顿网格，每步一格；未建模真实路网车速。

## 许可证

毕业设计/课程项目用途请遵循所在院系对代码与数据的要求；第三方 API 使用须遵守 DeepSeek 等服务条款。
