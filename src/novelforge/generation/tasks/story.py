"""Story Arc / Structural Unit 生成任务（V4-04 §21–§22）。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from novelforge.blueprint import StoryArcPayload, StructuralUnitPayload

from ..contracts import TaskSpec

STORY_ARC_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为这个故事生成全局故事弧：起始状态、激励事件、渐进复杂化、"
    "重大转折、中点、危机、高潮与收束。必须与前提交前提、世界与人物设定一致。"
    "不要写成正文。只输出 JSON。")

STRUCTURAL_UNIT_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为这一段结构生成一个 StructuralUnit（type 由任务给定：act / volume / arc）。"
    "必须给出该单元的目标、冲突、转折与结果；不要假设固定三幕或固定卷数，"
    "由任务输入决定单元数量与类型。只输出 JSON。")


def story_arc_spec() -> TaskSpec:
    return TaskSpec(
        task="story_arc", node_type="story_arc", output_model=StoryArcPayload,
        system_prompt=STORY_ARC_SYSTEM_PROMPT, requires_parent=False,
        capabilities=("creative", "structured_output", "large_context"),
        token_budget=1400, max_output_tokens=2200,
        context_types=("canon", "story_state", "episodic"),
        include_preferences=True, top_k=8, description="全局故事弧")


def structural_unit_spec() -> TaskSpec:
    return TaskSpec(
        task="structural_unit", node_type="structural_unit",
        output_model=StructuralUnitPayload,
        system_prompt=STRUCTURAL_UNIT_SYSTEM_PROMPT, requires_parent=True,
        parent_types=("story_arc", "structural_unit"),
        capabilities=("creative", "structured_output"), token_budget=800,
        max_output_tokens=1400, context_types=("canon",), include_preferences=True,
        top_k=6, description="结构单元（act / volume / arc）")


def story_arc_node_id() -> str:
    return "story_arc"


def structural_unit_node_id(unit_type: str, index: int) -> str:
    prefix = {"act": "act", "volume": "vol", "arc": "arc"}.get(unit_type, "unit")
    return f"{prefix}_{int(index):02d}"


def story_arc_task_input(*, premise: Mapping[str, Any] | None = None,
                         characters: Sequence[Mapping[str, Any]] = (),
                         world: Mapping[str, Any] | None = None,
                         extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": "生成全局故事弧（起承转合 / 中点 / 危机 / 高潮 / 收束）",
        "characters": [str(row.get("node_id") or "") for row in characters]}
    if premise:
        payload["premise"] = dict(premise)
    if world:
        payload["world"] = dict(world)
    if extra:
        payload.update(dict(extra))
    return payload


def structural_unit_task_input(*, unit_type: str, index: int, total: int,
                               story_arc: Mapping[str, Any] | None = None,
                               parent_id: str = "",
                               extra: Mapping[str, Any] | None = None
                               ) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": f"生成第 {index}/{total} 个结构单元（unit_type={unit_type}）",
        "unit_type": unit_type, "index": index, "total": total,
        "parent_id": parent_id}
    if story_arc:
        payload["story_arc"] = dict(story_arc)
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = [
    "STORY_ARC_SYSTEM_PROMPT", "STRUCTURAL_UNIT_SYSTEM_PROMPT",
    "story_arc_node_id", "story_arc_spec", "story_arc_task_input",
    "structural_unit_node_id", "structural_unit_spec", "structural_unit_task_input",
]

