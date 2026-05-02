"""
将仿真运行结果与 AI 分析报告持久化到项目目录。
目录（位于仓库根目录）：
  - saved_runs/          每次跑满步数后的 JSON 快照
  - saved_ai_analyses/   大模型生成的 Markdown 及元数据 JSON
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

REPO_ROOT = Path(__file__).resolve().parent.parent
SAVED_RUNS_DIR = REPO_ROOT / "saved_runs"
SAVED_AI_ANALYSES_DIR = REPO_ROOT / "saved_ai_analyses"

# 交给大模型时的「本项目基本情况」说明（可按课题修改）
RIDESIM_PROJECT_BRIEF_FOR_LLM = """
【项目概况】
这是一个离散网格上的网约车动态调度仿真程序（Python）。
- 城市为 GRID_SIZE×GRID_SIZE 网格；司机仅在「道路网络」上移动，接驾成本用道路上的最短步数（BFS）等指标近似。
- 订单按概率与时段生成，可与乘客手动下单混合；支持「新订单强制等待一步再抢单」等规则。
- 司机分为两类：① 规则司机，按配置策略（如 nearest / random / round_robin）与效率启发式抢单；
  ② 大语言模型（LLM）司机，根据结构化观测（候选订单、道路接驾距离、可行驶方向等）输出离散动作。
- 调度采用「先收集各司机意向，再统一冲突消解」的两阶段方式。
- 评价指标包括：订单完成率、司机总收入、总行驶距离、完成订单的等待步数统计、收入基尼系数与变异系数等。
下文 JSON 为一次或多次完整仿真结束后的统计快照，请结合上述背景解读与对比，不要编造未给出的数值。
""".strip()


def ensure_storage_dirs() -> None:
    SAVED_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SAVED_AI_ANALYSES_DIR.mkdir(parents=True, exist_ok=True)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError


def _config_snapshot() -> dict[str, Any]:
    return {
        "GRID_SIZE": config.GRID_SIZE,
        "NUM_DRIVERS": config.NUM_DRIVERS,
        "SIMULATION_STEPS": config.SIMULATION_STEPS,
        "RANDOM_SEED": config.RANDOM_SEED,
        "ORDER_PROBABILITY": config.ORDER_PROBABILITY,
        "USE_LLM_DRIVERS": config.USE_LLM_DRIVERS,
        "NUM_LLM_DRIVERS": config.NUM_LLM_DRIVERS,
        "NORMAL_STRATEGY": config.NORMAL_STRATEGY,
        "FORCE_ONE_STEP_BEFORE_DISPATCH": getattr(config, "FORCE_ONE_STEP_BEFORE_DISPATCH", False),
        "USE_ROAD_NETWORK": getattr(config, "USE_ROAD_NETWORK", True),
    }


def save_run_snapshot(sim) -> Path:
    """
    将当前已完成仿真的统计与配置写入 saved_runs/run_*.json。
    需在仿真跑满（current_step >= SIMULATION_STEPS）后调用。
    """
    ensure_storage_dirs()
    stats = sim.collect_statistics()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"run_{ts}_seed{config.RANDOM_SEED}.json"
    path = SAVED_RUNS_DIR / fname

    payload = {
        "saved_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": _config_snapshot(),
        "final_step": sim.current_step,
        "statistics": stats,
    }

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return path


def list_saved_run_files() -> list[Path]:
    ensure_storage_dirs()
    files = sorted(
        SAVED_RUNS_DIR.glob("run_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def list_saved_ai_files() -> list[Path]:
    ensure_storage_dirs()
    files = sorted(
        SAVED_AI_ANALYSES_DIR.glob("ai_analysis_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files


def load_run_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_ai_analysis_markdown(
    markdown: str,
    *,
    source_run_filenames: list[str],
    extra_meta: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """写入 Markdown 及同主名的 _meta.json。返回 (md_path, meta_path)。"""
    ensure_storage_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"ai_analysis_{ts}"
    md_path = SAVED_AI_ANALYSES_DIR / f"{base}.md"
    meta_path = SAVED_AI_ANALYSES_DIR / f"{base}_meta.json"

    md_path.write_text(markdown, encoding="utf-8")
    meta = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_run_files": source_run_filenames,
        **(extra_meta or {}),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, meta_path


def load_ai_meta_for(md_path: Path) -> dict[str, Any] | None:
    meta_path = md_path.with_name(md_path.stem + "_meta.json")
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def delete_saved_run(path: Path) -> None:
    if path.is_file() and path.resolve().parent == SAVED_RUNS_DIR.resolve():
        path.unlink()


def delete_ai_analysis(md_path: Path) -> None:
    if not md_path.is_file():
        return
    if md_path.resolve().parent != SAVED_AI_ANALYSES_DIR.resolve():
        return
    md_path.unlink(missing_ok=True)
    meta = md_path.with_name(md_path.stem + "_meta.json")
    meta.unlink(missing_ok=True)
