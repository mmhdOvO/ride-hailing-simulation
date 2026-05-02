"""
仿真结束后的「结果解读」大模型调用：与司机决策共用 DeepSeek / OpenAI 兼容配置。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from . import config
from .utils import driver as drv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

# 报告生成可略长于单步司机决策
ANALYSIS_TIMEOUT_SEC = 60
ANALYSIS_MAX_TOKENS = 2000


def _compact_stats_for_prompt(sim) -> dict[str, Any]:
    """收集用于报告的关键统计，控制 token 长度。"""
    stats = sim.collect_statistics()
    out: dict[str, Any] = {
        "当前步数": sim.current_step,
        "最大步数": config.SIMULATION_STEPS,
        "网格": f"{config.GRID_SIZE}x{config.GRID_SIZE}",
        "总订单数": stats.get("total_orders"),
        "完成订单数": stats.get("completed_orders"),
        "完成率%": round(stats.get("completion_rate", 0), 2),
        "司机总收入": stats.get("total_revenue"),
        "总行驶格数": stats.get("total_distance"),
        "启用大模型司机": config.USE_LLM_DRIVERS,
        "大模型司机数": min(config.NUM_LLM_DRIVERS, config.NUM_DRIVERS) if config.USE_LLM_DRIVERS else 0,
        "普通司机抢单策略": config.NORMAL_STRATEGY,
    }
    if "avg_waiting_time" in stats:
        out["完成订单_平均等待步数"] = round(stats["avg_waiting_time"], 2)
        out["完成订单_最长等待步数"] = stats.get("max_waiting_time")
        out["完成订单_最短等待步数"] = stats.get("min_waiting_time")
    if "revenue_gini" in stats:
        out["收入基尼系数"] = round(stats["revenue_gini"], 4)
        out["收入变异系数"] = round(stats.get("revenue_cv", 0), 4)
        out["司机收入最低"] = stats.get("min_revenue")
        out["司机收入最高"] = stats.get("max_revenue")

    # 收入榜前 12，含是否 LLM
    ranked = sorted(sim.drivers, key=lambda d: drv.revenue(d), reverse=True)[:12]
    out["司机收入榜_前12"] = [
        {
            "id": drv.driver_id(d),
            "类型": "llm" if drv.is_llm(d) else "rule",
            "收入": drv.revenue(d),
            "里程": drv.distance(d),
        }
        for d in ranked
    ]

    if config.USE_LLM_DRIVERS:
        llm_ds = [d for d in sim.drivers if drv.is_llm(d)]
        rule_ds = [d for d in sim.drivers if not drv.is_llm(d)]
        if llm_ds and rule_ds:
            lt = sum(drv.revenue(d) for d in llm_ds)
            rt = sum(drv.revenue(d) for d in rule_ds)
            ld = sum(drv.distance(d) for d in llm_ds)
            rd = sum(drv.distance(d) for d in rule_ds)
            out["LLM组_人数_总收入_收入每格"] = (len(llm_ds), lt, round(lt / max(1, ld), 3))
            out["规则组_人数_总收入_收入每格"] = (len(rule_ds), rt, round(rt / max(1, rd), 3))

    return out


def generate_post_run_analysis_markdown(sim) -> tuple[str, str | None]:
    """
    调用大模型对一次完整仿真结果做中文解读。

    返回: (markdown正文, 错误信息；成功时错误为 None)
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return (
            "",
            "未设置环境变量 DEEPSEEK_API_KEY（可在项目根目录 .env 中配置），无法生成 AI 分析。",
        )

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")

    payload = _compact_stats_for_prompt(sim)
    user_block = json.dumps(payload, ensure_ascii=False, indent=2)

    system_msg = (
        "你是交通仿真与网约车调度领域的分析助手。请根据给定的仿真实验统计结果，用专业但易懂的中文撰写分析报告。"
        "不要编造未提供的数据。使用 Markdown 输出，可含二级标题、列表、加粗重点；不要输出代码块包裹整篇报告。"
        "分析应包括：整体运营效果（完成率、收入与运力利用）、乘客体验（等待）、司机侧公平性（基尼/极差若存在）、"
        "若含 LLM 与规则司机则简要比对两者表现、以及 2～3 条可改进方向或实验局限。控制在 800 字左右。"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {
                    "role": "user",
                    "content": "以下为本次网格网约车仿真实验结束后的统计 JSON，请撰写「仿真实验分析报告」：\n\n" + user_block,
                },
            ],
            temperature=0.4,
            max_tokens=ANALYSIS_MAX_TOKENS,
            timeout=ANALYSIS_TIMEOUT_SEC,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return "", "大模型返回内容为空。"
        return text, None
    except Exception as e:
        return "", f"调用大模型失败: {e}"
