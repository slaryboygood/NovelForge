"""M2A：Story Planning IR versioning 回归（revision / branch / compare / promote / rollback）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    PlanningVersionError,
    PlanningVersionStore,
    StoryPlanningIR,
    merge_supplied,
    planning_digest,
    validate_planning_ir,
)

FIXTURE = Path("tests/fixtures/planning_ir/ONE_SENTENCE_EXAMPLE.json")


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan(**mutations) -> StoryPlanningIR:
    raw = _raw()
    raw.update(mutations)
    return validate_planning_ir(raw)


def _store_with_base():
    store = PlanningVersionStore(novel_id="demo_001")
    revision = store.add(_plan(), source="author", status="proposed", note="初稿")
    return store, revision


def test_revision_lineage_and_digest() -> None:
    store, first = _store_with_base()
    assert first.revision == 1
    assert first.parent_revision == ""
    assert first.digest == planning_digest(first.plan)
    second = store.commit(_plan(logline="第二版 logline"))
    assert second.revision == 2
    assert second.parent_revision == first.revision_id
    assert second.branch == "main"
    assert store.head("main").revision_id == second.revision_id
    lineage = store.lineage(second.revision_id)
    assert [item.revision for item in lineage] == [1, 2]


def test_compare_reports_field_level_diff_and_supplied_conflicts() -> None:
    store, first = _store_with_base()
    raw = _raw()
    raw["logline"] = "改过的 logline"
    raw["characters"][0]["external_goal"] = "被生成器改写"
    raw["characters"][0]["provenance"] = "generated"
    second = store.commit(validate_planning_ir(raw))
    diff = store.compare(first.revision_id, second.revision_id)
    assert diff.base_revision == first.revision_id
    assert diff.target_revision == second.revision_id
    assert any("logline" in path for path in diff.changed_paths())
    assert any("external_goal" in path for path in diff.changed_paths())
    assert any("external_goal" in path for path in diff.conflicts)
    assert diff.rows and diff.summary


def test_branch_pointer_tracks_independent_lines() -> None:
    store, first = _store_with_base()
    store.branch_pointer(first.revision_id, "alt")
    assert store.branches()["alt"] == first.revision_id
    alt = store.commit(_plan(logline="alt 线"), branch="alt")
    main = store.commit(_plan(logline="main 线"))
    assert store.head("alt").revision_id == alt.revision_id
    assert store.head("main").revision_id == main.revision_id
    assert [item.revision for item in store.lineage(alt.revision_id)] == [1, 2]
    with pytest.raises(PlanningVersionError) as error:
        store.branch_pointer(first.revision_id, "alt")
    assert error.value.code == "BRANCH_EXISTS"


def test_promote_creates_confirmed_revision_and_keeps_history() -> None:
    store, first = _store_with_base()
    promoted = store.promote(first.revision_id, note="作者确认")
    assert promoted.status == "confirmed"
    assert promoted.revision == 2
    assert promoted.parent_revision == first.revision_id
    assert promoted.digest == first.digest
    assert store.get(first.revision_id).status == "proposed"
    assert store.head("main").revision_id == promoted.revision_id


def test_rollback_restores_content_and_marks_superseded() -> None:
    store, first = _store_with_base()
    second = store.commit(_plan(logline="被放弃的版本"))
    rolled = store.rollback(first.revision_id, note="回到初稿")
    assert rolled.status == "rolled_back"
    assert rolled.revision == 3
    assert rolled.parent_revision == second.revision_id
    assert rolled.digest == first.digest
    assert store.get(second.revision_id).status == "superseded"
    assert [item.revision for item in store.lineage(rolled.revision_id)] == [1, 2, 3]


def test_promote_can_target_branch_head() -> None:
    store, first = _store_with_base()
    released = store.promote(first.revision_id, target_branch="release")
    assert store.head("release").revision_id == released.revision_id
    assert released.branch == "release"
    assert store.head("main").revision_id == first.revision_id


def test_merge_supplied_protects_author_entries() -> None:
    base = _plan()
    raw = _raw()
    raw["characters"][0]["external_goal"] = "生成器改写的目标"
    raw["characters"][0]["provenance"] = "generated"
    raw["plot_nodes"].append({"node_id": "NODE_NEW", "purpose": "生成的新节点",
                              "conflict": "新冲突", "state_change": "新状态",
                              "provenance": "generated"})
    merged, protected = merge_supplied(base, validate_planning_ir(raw))
    assert protected == ["CHAR_LIN"]
    assert merged.characters[0].external_goal == base.characters[0].external_goal
    assert any(node.node_id == "NODE_NEW" for node in merged.plot_nodes)


def test_merge_supplied_keeps_generated_entries_updatable() -> None:
    base = _plan()
    raw = _raw()
    raw["plot_nodes"][1]["conflict"] = "生成器更新的冲突"
    merged, protected = merge_supplied(base, validate_planning_ir(raw))
    assert protected == []
    assert merged.plot_nodes[1].conflict == "生成器更新的冲突"


def test_version_store_rejects_unknown_revision_and_novel_mismatch() -> None:
    store, _ = _store_with_base()
    with pytest.raises(PlanningVersionError) as error:
        store.get("PREV_GHOST")
    assert error.value.code == "REVISION_NOT_FOUND"
    with pytest.raises(PlanningVersionError) as mismatch:
        store.add(_plan(novel_id="other_novel"))
    assert mismatch.value.code == "NOVEL_ID_MISMATCH"
