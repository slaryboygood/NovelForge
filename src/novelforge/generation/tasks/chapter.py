"""Chapter Card 生成任务（V4-04 §23）。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from novelforge.blueprint import ChapterCardPayload

from ..contracts import TaskSpec

CHAPTER_SYSTEM_PROMPT = (
    "你是故事蓝图助手。为这个结构单元生成一张 Chapter Card：目标、POV、出场人物、地点、"
    "冲突、转折、结果、结尾钩子、需要埋设的 setup 与需要回收的 payoff，"
    "以及**计划中的** StoryState 变化意图（state_change_intent，只是计划，不是已发生事实）。"
    "标题必须是内容（这一章真正发生了什么），不得使用字段标签或模板占位。"
    "不要写成正文。只输出 JSON。")


def chapter_spec() -> TaskSpec:
    return TaskSpec(
        task="chapter", node_type="chapter", output_model=ChapterCardPayload,
        system_prompt=CHAPTER_SYSTEM_PROMPT, requires_parent=True,
        parent_types=("structural_unit", "story_arc"),
        capabilities=("creative", "structured_output"), token_budget=900,
        max_output_tokens=1600, context_types=("canon", "story_state", "episodic"),
        include_preferences=True, top_k=7, description="章节卡（不生成 prose）")


def chapter_node_id(index: int) -> str:
    return f"ch_{int(index):03d}"


def chapter_task_input(*, parent: Mapping[str, Any], index: int, total: int,
                       characters: Sequence[Mapping[str, Any]] = (),
                       setup_ids: Sequence[str] = (),
                       extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "task": f"生成第 {index}/{total} 章 Chapter Card",
        "parent_id": str(parent.get("node_id") or ""),
        "parent": dict(parent), "index": index, "total": total,
        "characters": [str(row.get("node_id") or "") for row in characters],
        "open_setups": [str(value) for value in setup_ids]}
    if extra:
        payload.update(dict(extra))
    return payload


__all__ = ["CHAPTER_SYSTEM_PROMPT", "chapter_node_id", "chapter_spec",
           "chapter_task_input"]

