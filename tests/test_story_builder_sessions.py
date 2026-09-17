from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from novelforge.story_builder import (
    BuilderStatus,
    StoryBuilderSession,
    StorySessionError,
    StorySessionManager,
    StorySessionRepository,
    StoryStep,
)


@pytest.fixture
def repository(tmp_path: Path) -> StorySessionRepository:
    return StorySessionRepository(tmp_path)


@pytest.fixture
def manager(repository: StorySessionRepository) -> StorySessionManager:
    from novelforge.story_builder import load_story_catalog

    project_root = Path(__file__).resolve().parents[1]
    return StorySessionManager(repository, load_story_catalog(project_root))


def test_create_persists_and_loads_session(repository: StorySessionRepository) -> None:
    created = repository.create("silicon_rise", session_id="session_001")
    loaded = repository.load("session_001")

    assert loaded == created
    assert loaded.status == BuilderStatus.CREATED
    assert loaded.current_step == StoryStep.READER_EXPERIENCE
    assert repository.path_for("session_001").is_file()


def test_generated_session_id_is_safe(repository: StorySessionRepository) -> None:
    session = repository.create("silicon_rise")

    assert session.session_id.startswith("sb_")
    assert repository.path_for(session.session_id).parent == repository.sessions_dir


def test_save_requires_matching_selection_version(repository: StorySessionRepository) -> None:
    created = repository.create("silicon_rise", session_id="session_001")
    changed = created.model_copy(
        update={
            "status": BuilderStatus.CONFIGURING,
            "current_step": StoryStep.WORLDVIEW,
            "selection_version": 1,
        }
    )

    saved = repository.save(changed, expected_selection_version=0)

    assert saved.selection_version == 1
    assert repository.load("session_001") == saved

    with pytest.raises(StorySessionError) as conflict:
        repository.save(changed, expected_selection_version=0)
    assert conflict.value.code == "SESSION_VERSION_CONFLICT"
    assert conflict.value.details[0]["actual_selection_version"] == 1


def test_stale_save_does_not_modify_current_file(repository: StorySessionRepository) -> None:
    created = repository.create("silicon_rise", session_id="session_001")
    current = repository.save(
        created.model_copy(update={"selection_version": 1}),
        expected_selection_version=0,
    )
    before = repository.path_for("session_001").read_bytes()

    with pytest.raises(StorySessionError):
        repository.save(
            created.model_copy(update={"selection_version": 2}),
            expected_selection_version=0,
        )

    assert repository.path_for("session_001").read_bytes() == before
    assert repository.load("session_001") == current


def test_atomic_replace_failure_keeps_previous_session_and_cleans_temp(
    repository: StorySessionRepository,
) -> None:
    created = repository.create("silicon_rise", session_id="session_001")
    path = repository.path_for("session_001")
    before = path.read_bytes()
    changed = created.model_copy(update={"selection_version": 1})

    with patch("novelforge.story_builder.sessions.os.replace", side_effect=OSError("磁盘失败")):
        with pytest.raises(OSError):
            repository.save(changed, expected_selection_version=0)

    assert path.read_bytes() == before
    assert list(repository.sessions_dir.glob("*.tmp")) == []


def test_latest_session_for_project_can_resume(repository: StorySessionRepository) -> None:
    first = repository.create("silicon_rise", session_id="session_001")
    second = repository.create("silicon_rise", session_id="session_002")
    repository.create("another_project", session_id="session_003")
    first = repository.save(
        first.model_copy(update={"selection_version": 1}),
        expected_selection_version=0,
    )

    assert repository.latest_for_project("silicon_rise") == first
    assert [item.session_id for item in repository.list_for_project("silicon_rise")] == [
        first.session_id,
        second.session_id,
    ]


def test_missing_corrupt_and_mismatched_sessions_have_readable_errors(
    repository: StorySessionRepository,
) -> None:
    with pytest.raises(StorySessionError) as missing:
        repository.load("session_404")
    assert missing.value.code == "SESSION_NOT_FOUND"

    path = repository.path_for("session_bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(StorySessionError) as broken:
        repository.load("session_bad")
    assert broken.value.code == "SESSION_JSON_INVALID"

    session = StoryBuilderSession(session_id="session_other", project_id="silicon_rise")
    path.write_text(
        json.dumps({"schema_version": 1, "session": session.model_dump(mode="json")}),
        encoding="utf-8",
    )
    with pytest.raises(StorySessionError) as mismatch:
        repository.load("session_bad")
    assert mismatch.value.code == "SESSION_ID_MISMATCH"


@pytest.mark.parametrize("invalid_id", ["../escape", "bad/id", "", "ab"])
def test_invalid_session_id_cannot_escape_storage(
    repository: StorySessionRepository,
    invalid_id: str,
) -> None:
    with pytest.raises(StorySessionError) as caught:
        repository.load(invalid_id)

    assert caught.value.code == "SESSION_ID_INVALID"


def test_sessions_directory_must_stay_inside_project(tmp_path: Path) -> None:
    with pytest.raises(StorySessionError) as caught:
        StorySessionRepository(tmp_path, tmp_path.parent / "outside_sessions")

    assert caught.value.code == "SESSION_PATH_OUTSIDE_PROJECT"


def test_legacy_session_without_newer_design_fields_still_loads(
    repository: StorySessionRepository,
) -> None:
    session = repository.create("silicon_rise", session_id="session_legacy")
    stored = {"schema_version": 1, "session": session.model_dump(mode="json")}
    del stored["session"]["design_choices"]
    del stored["session"]["needs_review_steps"]
    repository.path_for("session_legacy").write_text(json.dumps(stored), encoding="utf-8")

    loaded = repository.load("session_legacy")
    assert loaded.design_choices == {}
    assert loaded.needs_review_steps == []
    assert loaded.selections == []
    saved = repository.save(
        loaded.model_copy(update={"selection_version": 1}),
        expected_selection_version=0,
    )
    assert saved.selection_version == 1
    assert repository.load("session_legacy").design_choices == {}


def test_setting_step_selection_advances_and_creates_history(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")

    changed = manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_growth_adventure"],
        expected_selection_version=0,
    )

    assert changed.selection_version == 1
    assert changed.current_step == StoryStep.WORLDVIEW
    assert changed.completed_steps == [StoryStep.READER_EXPERIENCE]
    assert changed.status == BuilderStatus.CONFIGURING
    assert [item.selection_version for item in repository.history_for("session_001")] == [0, 1]


def test_direct_ineligible_selection_is_rejected_without_new_version(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")
    manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_growth_adventure"],
        expected_selection_version=0,
    )

    manager.set_step_selections('session_001', StoryStep.WORLDVIEW,
                                option_ids=['world_modern_supernatural'], expected_selection_version=1)
    with pytest.raises(StorySessionError) as caught:
        manager.set_step_selections(
            "session_001",
            StoryStep.BACKGROUND,
            option_ids=["background_ruined_board"],
            expected_selection_version=2,
        )

    assert caught.value.code == "SELECTION_CONFLICT"
    assert repository.load("session_001").selection_version == 2


def test_changing_earlier_step_preserves_downstream_and_marks_review(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")
    manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_growth_adventure"],
        expected_selection_version=0,
    )
    manager.set_step_selections(
        "session_001",
        StoryStep.WORLDVIEW,
        option_ids=["world_silicon_mmo"],
        expected_selection_version=1,
    )

    changed = manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_relationship_drama"],
        expected_selection_version=2,
    )

    assert changed.selection_version == 3
    assert {item.option_id for item in changed.selections} == {
        "experience_relationship_drama",
        "world_silicon_mmo",
    }
    assert StoryStep.WORLDVIEW in changed.needs_review_steps
    assert StoryStep.READER_EXPERIENCE not in changed.needs_review_steps
    assert changed.status == BuilderStatus.NEEDS_REVIEW
    assert changed.current_step == StoryStep.WORLDVIEW

    history = repository.history_for("session_001")
    assert [item.selection_version for item in history] == [0, 1, 2, 3]
    assert "experience_growth_adventure" in {
        item.option_id for item in history[-2].selections
    }


def test_reconfirming_downstream_clears_review_marker(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")
    manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_growth_adventure"],
        expected_selection_version=0,
    )
    manager.set_step_selections(
        "session_001",
        StoryStep.WORLDVIEW,
        option_ids=["world_silicon_mmo"],
        expected_selection_version=1,
    )
    manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_mystery_exploration"],
        expected_selection_version=2,
    )

    changed = manager.set_step_selections(
        "session_001",
        StoryStep.WORLDVIEW,
        option_ids=["world_silicon_mmo"],
        expected_selection_version=3,
    )

    assert changed.needs_review_steps == []
    assert changed.status == BuilderStatus.CONFIGURING
    assert changed.current_step == StoryStep.BACKGROUND


def test_custom_selection_advances_without_catalog_option(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")

    changed = manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        custom_texts=["冷峻但保留希望的探索"],
        expected_selection_version=0,
    )

    assert changed.current_step == StoryStep.WORLDVIEW
    assert changed.selections[0].custom_text == "冷峻但保留希望的探索"
    assert changed.selections[0].option_id is None


def test_go_back_persists_navigation_without_new_selection_version(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")
    manager.set_step_selections(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        option_ids=["experience_growth_adventure"],
        expected_selection_version=0,
    )

    returned = manager.go_back(
        "session_001",
        StoryStep.READER_EXPERIENCE,
        expected_selection_version=1,
    )

    assert returned.current_step == StoryStep.READER_EXPERIENCE
    assert returned.selection_version == 1
    with pytest.raises(StorySessionError) as caught:
        manager.go_back(
            "session_001",
            StoryStep.BACKGROUND,
            expected_selection_version=1,
        )
    assert caught.value.code == "BACK_TARGET_INVALID"


def test_step_replacement_rejects_wrong_step_and_count(
    repository: StorySessionRepository,
    manager: StorySessionManager,
) -> None:
    repository.create("silicon_rise", session_id="session_001")

    with pytest.raises(StorySessionError) as mismatch:
        manager.set_step_selections(
            "session_001",
            StoryStep.READER_EXPERIENCE,
            option_ids=["world_silicon_mmo"],
            expected_selection_version=0,
        )
    assert mismatch.value.code == "SELECTION_STEP_MISMATCH"

    with pytest.raises(StorySessionError) as count:
        manager.set_step_selections(
            "session_001",
            StoryStep.READER_EXPERIENCE,
            option_ids=[],
            expected_selection_version=0,
        )
    assert count.value.code == "SELECTION_COUNT_INVALID"
