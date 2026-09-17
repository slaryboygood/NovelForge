"""StoryState retrieval（V4-03 §6）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import MemoryQuery
from support import build_novel, service_for


def test_story_state_items_cover_current_state(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    items = service.index.items("novel_alpha", source_types=("story_state",))
    kinds = {str(item.metadata.get("kind")) for item in items}
    assert {"timeline", "location", "character", "resource", "promise"} <= kinds


def test_story_state_is_not_duplicated_as_truth(tmp_path: Path) -> None:
    """Memory 不维护第二套 StoryState：条目全部指向 story_state 来源。"""

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    for item in service.index.items("novel_alpha"):
        assert item.source.source_id
        assert item.source.source_type in {
            "story_state", "canon_fact", "canon_entity", "episode", "semantic",
            "preference"}


def test_story_state_carries_revision(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    items = service.index.items("novel_alpha", source_types=("story_state",))
    assert items and all(item.source.revision is not None for item in items)


def test_open_promise_and_conflict_are_marked_open(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(novel_id="novel_alpha",
                                        entities=("hero", "rival")))
    open_items = [item for item in result.items if item.metadata.get("open")]
    assert open_items, "未完成承诺 / 未解决冲突必须被标记为 open（供 setup/payoff 使用）"


def test_story_state_retrieval_is_deterministic(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    query = MemoryQuery(novel_id="novel_alpha", entities=("hero",),
                        source_types=("story_state",))
    first = [item.memory_id for item in service.search(query).items]
    second = [item.memory_id for item in service.search(query).items]
    assert first == second

