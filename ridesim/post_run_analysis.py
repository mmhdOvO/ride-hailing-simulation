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
from .run_persistence import RIDESIM_PROJECT_BRIEF_FOR_LLM, load_run_json
from .utils import driver as drv

_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

# 报告生成可略长于单步司机决策
ANALYSIS_TIMEOUT_SEC = 60
ANALYSIS_MAX_TOKENS = 2000
BATCH_ANALYSIS_TIMEOUT_SEC = 120
BATCH_ANALYSIS_MAX_TOKENS = 4000


def _analysis_model_name() -> str:
    """跑满后的报告生成：默认 V4-Pro；优先 DEEPSEEK_MODEL_ANALYSIS，否则回落 DEEPSEEK_MODEL。"""
    return os.getenv("DEEPSEEK_MODEL_ANALYSIS") or os.getenv(
        "DEEPSEEK_MODEL", "deepseek-v4-pro"
    )


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
    model = _analysis_model_name()
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


def generate_batch_analysis_markdown(run_paths: list[Path]) -> tuple[str, str | None]:
    """
    读取若干已保存的 run_*.json，连同项目背景说明一并交给大模型做对比与解读。
    """
    if not run_paths:
        return "", "未选择任何仿真记录文件。"

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return (
            "",
            "未设置 DEEPSEEK_API_KEY，请在项目根目录 .env 中配置。",
        )

    runs_payload: list[dict[str, Any]] = []
    for p in run_paths:
        try:
            data = load_run_json(p)
            runs_payload.append(
                {
                    "文件名": p.name,
                    "保存时间_UTC": data.get("saved_at_utc"),
                    "配置": data.get("config"),
                    "结束步数": data.get("final_step"),
                    "统计指标": data.get("statistics"),
                }
            )
        except Exception as e:
            return "", f"读取 {p.name} 失败: {e}"

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = _analysis_model_name()
    client = OpenAI(api_key=api_key, base_url=f"{base_url}/v1")

    user_body = (
        RIDESIM_PROJECT_BRIEF_FOR_LLM
        + "\n\n以下是选中的一次或多次仿真实验 JSON 数组，请撰写综合分析报告：\n\n"
        + json.dumps(runs_payload, ensure_ascii=False, indent=2)
    )

    system_msg = (
        "你是交通仿真与网约车调度领域的分析助手。用户已提供【项目概况】与【多次实验的统计 JSON】。"
        "请用中文 Markdown 撰写报告：若有多条记录，请对比差异（完成率、收入、等待、公平性等），分析可能原因（配置/随机种子/策略）；"
        "若仅一条，则做深度解读。不要编造数据中不存在的数字。可含二级标题与列表，篇幅约 1000～1500 字。"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_body},
            ],
            temperature=0.35,
            max_tokens=BATCH_ANALYSIS_MAX_TOKENS,
            timeout=BATCH_ANALYSIS_TIMEOUT_SEC,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return "", "大模型返回内容为空。"
        return text, None
    except Exception as e:
        return "", f"调用大模型失败: {e}"
