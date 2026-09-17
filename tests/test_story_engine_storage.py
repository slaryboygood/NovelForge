from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.story_engine import (
    ResourceStock,
    StoryState,
    StoryStateRepository,
    StoryStateStorageError,
)


LEGACY_ADVENTURE = {
    "blueprint_id": "bp_legacy",
    "blueprint_version": 1,
    "revision": 2,
    "rules_version": 2,
    "branch_id": "main",
    "supplies": 3,
    "ally": True,
    "clue": False,
    "trust": 1,
    "debt": 0,
    "facts": ["receipt"],
    "arc_finished": False,
    "history": [{"scene": "行动的条件", "choice_id": "help", "choice": "先帮同行者", "result": "获得协助"}],
}


def test_story_state_repository_round_trip_and_paths(tmp_path: Path) -> None:
    repository = StoryStateRepository(tmp_path)
    state = StoryState(novel_id="novel_a",
                       resources={"supplies": ResourceStock(id="supplies", amount=1, unit="份")},
                       flags={"journey_revision": 1})
    assert not repository.exists("bp_demo", 1)
    repository.save(state, "bp_demo", 1)
    assert repository.exists("bp_demo", 1)
    assert repository.load("bp_demo", 1) == state
    branch = Path(repository.path_for("bp_demo", 1, "branch_" + "a" * 32))
    assert branch.name == "v000001_branch_" + "a" * 32 + ".json"
    for bad in ["../escape", "bp bad", ""]:
        with pytest.raises(StoryStateStorageError):
            repository.path_for(bad, 1)
    with pytest.raises(StoryStateStorageError):
        repository.path_for("bp_demo", 0)
    with pytest.raises(StoryStateStorageError):
        repository.path_for("bp_demo", 1, "other")
    with pytest.raises(StoryStateStorageError):
        StoryStateRepository(tmp_path, tmp_path.parent / "outside_state")
    with pytest.raises(StoryStateStorageError):
        repository.load("bp_missing", 1)


def test_migrate_from_legacy_adventure_without_touching_it(tmp_path: Path) -> None:
    repository = StoryStateRepository(tmp_path)
    state, migrated = repository.load_or_migrate(LEGACY_ADVENTURE, "bp_legacy", 1, novel_id="novel_a")
    assert migrated is True
    assert state.novel_id == "novel_a"
    assert state.resources["supplies"].amount == 3
    assert state.knowledge[0].id == "receipt"
    assert state.flags["legacy.ally"] is True
    assert state.legacy["adventure"]["trust"] == 1  # 无法无损映射的字段原样保留
    repository.save(state, "bp_legacy", 1)
    loaded, migrated_again = repository.load_or_migrate(LEGACY_ADVENTURE, "bp_legacy", 1, novel_id="novel_a")
    assert migrated_again is False and loaded == state
    assert not (tmp_path / "novel" / "authoring" / "story_builder" / "adventures").exists()


def test_migrate_without_legacy_payload_starts_empty(tmp_path: Path) -> None:
    repository = StoryStateRepository(tmp_path)
    state, migrated = repository.load_or_migrate(None, "bp_empty", 1)
    assert migrated is True
    assert state.resources == {} and state.knowledge == [] and state.flags == {}
    assert repository.delete("bp_empty", 1) is False
