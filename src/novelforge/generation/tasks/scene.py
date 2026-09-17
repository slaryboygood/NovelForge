"""Scene Card 生成任务（V4-04 §24–§25、§28）。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from novelforge.blueprint import SceneCardPayload

from ..contracts import TaskSpec

SCENE_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为这一章生成一张 Scene Card，必须回答"
    "「如果删掉这一场，故事损失什么？」：scene_purpose、人物目标、冲突、升级、转折、结果、"
    "信息释放、人物与关系变化、setup/payoff 关联、**计划中的**状态转换意图、下一步钩子，"
    "以及 story_function（结构化枚举，可多选）。"
    "不得写成场景正文，不得发明既定事实或角色身份。只输出 JSON。")


def scene_spec() -> TaskSpec:
    return TaskSpec(
        task="scene", node_type="scene", output_model=SceneCardPayload,
        system_prompt=SCENE_SYSTEM_PROMPT, requires_parent=True,
        parent_types=("chapter",),
        capabilities=("creative", "structured_output"), token_budget=800,
        max_output_tokens=1600, context_types=("canon", "story_state", "episodic"),
        include_preferences=True, top_k=8, description="场景卡（最小故事单元）")


def scene_node_id(chapter_index: int, sequence: int) -> str:
    return f"sc_{int(chapter_index):03d}_{int(sequence):02d}"


def scene_task_input(*, chapter: Mapping[str, Any], sequence: int, total: int,
                     characters: Sequence[Mapping[str, Any]] = (),
                     setup_ids: Sequence[str] = (),
                     previous_scenes: Sequence[Mapping[str, Any]] = (),
                     extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": f"生成本章第 {sequence}/{total} 场 Scene Card",
        "parent_id": str(chapter.get("node_id") or ""),
        "chapter": dict(chapter), "sequence": sequence, "total": total,
        "characters": [str(row.get("node_id") or "") for row in characters],
        "open_setups": [str(value) for value in setup_ids],
        "previous_scenes": [
            {"node_id": row.get("node_id"), "purpose": row.get("scene_purpose"),
             "outcome": row.get("outcome")} for row in previous_scenes]}
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = ["SCENE_SYSTEM_PROMPT", "scene_node_id", "scene_spec", "scene_task_input"]

