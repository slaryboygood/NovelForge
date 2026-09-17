"""Episodic Memory（V4-03 §7）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.memory import MemoryQuery
from novelforge.memory.episodic import EpisodeEntry, EpisodicStore, derive_episodes
from support import build_novel, service_for


def _state(tmp_path: Path, novel_id: str = "novel_alpha"):
    from novelforge.story_engine.creator import resolve_creator_context

    return resolve_creator_context(tmp_path, novel_id).state


def test_derive_episodes_from_story_state_effects(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    episodes = derive_episodes(_state(tmp_path), revision=2)
    assert {entry.episode_id for entry in episodes} == {"ep_act_betray", "ep_act_probe"}
    betrayal = next(entry for entry in episodes if entry.episode_id == "ep_act_betray")
    assert betrayal.who_acted == ("rival",)
    assert betrayal.relationship_changes == ("rival→hero=-2",)
    assert betrayal.source_ids
    assert betrayal.memory_schema_version >= 1
    assert betrayal.created_at


def test_episodes_are_rebuildable_and_deterministic(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    # 传入固定 created_at → derive_episodes 成为纯函数
    first = derive_episodes(_state(tmp_path), created_at="T0")
    second = derive_episodes(_state(tmp_path), created_at="T0")
    assert [entry.as_dict() for entry in first] == \
        [entry.as_dict() for entry in second], "派生 episode 必须可重复构建"

    # 重新 rebuild 后内容等价（created_at 允许变化）
    service_a = service_for(tmp_path, "novel_alpha")
    service_b = service_for(tmp_path, "novel_alpha")
    strip = lambda rows: [  # noqa: E731
        {key: value for key, value in row.items() if key != "created_at"} for row in rows]
    assert strip(service_a.episodic.digest_rows("novel_alpha")) == \
        strip(service_b.episodic.digest_rows("novel_alpha"))


def test_episodic_store_accepts_blueprint_sourced_episodes(tmp_path: Path) -> None:
    """未来 Story Blueprint 只需同一契约：source_ids + revision（§27）。"""

    store = EpisodicStore()
    store.add(EpisodeEntry(episode_id="ep_scene_001", novel_id="novel_alpha",
                           revision=7, scene_id="sc_001", chapter_id="ch_001",
                           what_happened="主角在车站发现备用电源被破坏",
                           who_acted=("hero",), setup=("power_sabotage",),
                           source_ids=("sc_001@7", "ch_001@3"),
                           source_type="blueprint_node", tick=5))
    entries = store.for_novel("novel_alpha")
    assert entries and entries[0].source_type == "blueprint_node"
    item = entries[0].to_item()
    assert item.source.source_type == "episode"
    assert item.source.metadata["source_ids"] == ["sc_001@7", "ch_001@3"]


def test_episodic_memory_never_reads_prose_paths(tmp_path: Path) -> None:
    """来源必须是 Blueprint / Scene / Chapter / effect，不得指向旧正文。"""

    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    for item in service.index.items("novel_alpha", source_types=("episode",)):
        assert "novel/final" not in item.text
        assert "prose" not in item.text.lower()
        assert item.source.metadata.get("source_ids") is not None


def test_episodes_are_retrievable_as_recent_history(tmp_path: Path) -> None:
    build_novel(tmp_path, "novel_alpha", title="阿尔法计划", fact_text="主角不会使用枪械")
    service = service_for(tmp_path, "novel_alpha")
    result = service.search(MemoryQuery(novel_id="novel_alpha",
                                        source_types=("episode",)))
    assert result.items, "episode 必须进入检索索引"
    assert all(item.memory_type == "episodic" for item in result.items)
