"""Premise / Theme 生成任务（V4-04 §17）。"""

from __future__ import annotations

from typing import Any, Mapping

from novelforge.blueprint import PremisePayload, ThemePayload

from ..contracts import TaskSpec

PREMISE_SYSTEM_PROMPT = (
    "你是故事蓝图助手。基于给定创意与可用上下文，产出一个**可验证、可修订**的前提（premise）。"
    "必须给出中心冲突、主角目标、代价、戏剧问题与故事承诺；不得写成完整正文，"
    "不得发明上下文中不存在的既定事实。只输出 JSON。")

THEME_SYSTEM_PROMPT = (
    "你是故事蓝图助手。基于前提与上下文，给出主题（theme）与反题（counter_theme），"
    "并列出最多 6 个母题。不要写成正文，不要引入新的既定事实。只输出 JSON。")


def premise_spec() -> TaskSpec:
    return TaskSpec(
        task="premise", node_type="premise", output_model=PremisePayload,
        system_prompt=PREMISE_SYSTEM_PROMPT,
        capabilities=("creative", "structured_output"), token_budget=700,
        max_output_tokens=1200, context_types=("canon", "story_state"),
        include_preferences=True, top_k=5, description="故事前提与中心冲突")


def theme_spec() -> TaskSpec:
    return TaskSpec(
        task="theme", node_type="theme", output_model=ThemePayload,
        system_prompt=THEME_SYSTEM_PROMPT,
        requires_parent=False,
        capabilities=("creative", "structured_output"), token_budget=600,
        max_output_tokens=900, context_types=("canon",),
        include_preferences=True, top_k=4, description="主题与母题")


def premise_node_id() -> str:
    return "premise"


def theme_node_id() -> str:
    return "theme"


def premise_task_input(*, brief: Mapping[str, Any] | None = None,
                       extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = {"task": "生成故事前提（premise）：中心冲突 / 主角目标 / 代价 / 戏剧问题 / 故事承诺"}
    if brief:
        payload["brief"] = dict(brief)
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = ["PREMISE_SYSTEM_PROMPT", "THEME_SYSTEM_PROMPT", "premise_node_id",
           "premise_spec", "premise_task_input", "theme_node_id", "theme_spec"]

