"""Character / Character Arc 生成任务（V4-04 §18–§19）。"""

from __future__ import annotations

from typing import Any, Mapping

from novelforge.blueprint import CharacterArcPayload, CharacterPayload, slug

from ..contracts import TaskSpec

CHARACTER_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为这个故事生成一个有明确欲望、需求、恐惧、错误信念、长处与缺陷的人物。"
    "禁止套用固定原型文案；每一条都必须与给定的前提和世界约束相关。"
    "不要发明既定事实，不要写正文。只输出 JSON。")

CHARACTER_ARC_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为一个已有人物生成人物弧（character arc）：起始状态、内在冲突、"
    "外部压力、关键转折、中点变化、危机、高潮抉择、结束状态。"
    "必须与已给定的人物设定一致，不得改变人物身份。只输出 JSON。")


def character_spec() -> TaskSpec:
    return TaskSpec(
        task="character", node_type="character", output_model=CharacterPayload,
        system_prompt=CHARACTER_SYSTEM_PROMPT,
        capabilities=("creative", "structured_output"), token_budget=700,
        max_output_tokens=1400, context_types=("canon",), include_preferences=True,
        top_k=6, description="人物设定（是什么）")


def character_arc_spec() -> TaskSpec:
    return TaskSpec(
        task="character_arc", node_type="character_arc",
        output_model=CharacterArcPayload, system_prompt=CHARACTER_ARC_SYSTEM_PROMPT,
        requires_parent=True, parent_types=("character",),
        capabilities=("creative", "structured_output"), token_budget=800,
        max_output_tokens=1600, context_types=("canon", "episodic"),
        include_preferences=True, top_k=6, description="人物弧（如何变化）")


def character_node_id(index: int, name: str) -> str:
    """系统分配 id（模型不得自造，§47）。"""

    stem = slug(name, limit=18, fallback="")
    if not stem:
        # 非 ASCII 名称（例如中文）：用稳定短摘要代替，避免所有角色都叫 "role"
        import hashlib

        stem = hashlib.sha1(str(name or "").encode("utf-8")).hexdigest()[:6]
    return f"char_{int(index):02d}_{stem}"[:64]


def character_arc_node_id(character_id: str) -> str:
    return f"arc_{character_id}"[:64]


def character_task_input(*, premise: Mapping[str, Any] | None = None,
                         world: Mapping[str, Any] | None = None,
                         index: int = 1, kind: str = "npc",
                         extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": f"生成第 {index} 个人物设定（kind={kind}）",
        "index": index, "kind": kind}
    if premise:
        payload["premise"] = dict(premise)
    if world:
        payload["world"] = dict(world)
    if extra:
        payload.update(dict(extra))
    return payload


def character_arc_task_input(*, character: Mapping[str, Any],
                             premise: Mapping[str, Any] | None = None,
                             extra: Mapping[str, Any] | None = None
                             ) -> dict[str, Any]:
    payload: dict[str, Any] = {"task": "生成该人物的人物弧",
                               "character": dict(character),
                               "characters": [str(character.get("node_id") or "")]}
    if premise:
        payload["premise"] = dict(premise)
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = [
    "CHARACTER_ARC_SYSTEM_PROMPT", "CHARACTER_SYSTEM_PROMPT",
    "character_arc_node_id", "character_arc_spec", "character_arc_task_input",
    "character_node_id", "character_spec", "character_task_input",
]
