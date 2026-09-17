"""World 生成任务（V4-04 §20）。"""

from __future__ import annotations

from typing import Any, Mapping

from novelforge.blueprint import WorldPayload

from ..contracts import TaskSpec

WORLD_SYSTEM_PROMPT = (
    "你是故事蓝图助手。只生成**对故事有用的世界约束**：规则、地点、势力、资源、"
    "技术或超自然设定、社会限制、冲突来源、与故事相关的历史。"
    "不要写百科条目，不要发明与已确认 Canon 冲突的事实。只输出 JSON。")


def world_spec() -> TaskSpec:
    return TaskSpec(
        task="world", node_type="world", output_model=WorldPayload,
        system_prompt=WORLD_SYSTEM_PROMPT, requires_parent=False,
        capabilities=("creative", "structured_output"), token_budget=900,
        max_output_tokens=1800, context_types=("canon", "story_state"),
        include_preferences=True, top_k=6, description="对故事有用的世界约束")


def world_node_id() -> str:
    return "world"


def world_task_input(*, premise: Mapping[str, Any] | None = None,
                     extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"task": "生成世界约束（规则 / 地点 / 势力 / 资源 / 冲突来源）"}
    if premise:
        payload["premise"] = dict(premise)
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = ["WORLD_SYSTEM_PROMPT", "world_node_id", "world_spec", "world_task_input"]

