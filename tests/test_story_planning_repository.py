"""M2B：PlanningRepository 回归（persistence / immutability / branch / diff / conflict）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.planning import (
    PlanningConflict,
    PlanningConflictError,
    PlanningRepository,
    PlanningRepositoryError,
    planning_digest,
    validate_planning_ir,
)

FIXTURE = Path("tests/fixtures/planning_ir/ONE_SENTENCE_EXAMPLE.json")


def _raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _plan(**overrides):
    raw = _raw()
    raw.update(overrides)
    return validate_planning_ir(raw)


def _repo(tmp_path: Path) -> PlanningRepository:
    return PlanningRepository(tmp_path, "demo_001")


def test_revision_persistence_and_round_trip(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    record = repo.create(_plan(), status="proposed", note="R1")
    assert record.revision == 1
    assert record.parent_revision_id == ""
    assert record.branch_id == "main"
    assert record.content_digest == planning_digest(record.plan)
    loaded = repo.load(record.revision_id)
    assert loaded.content_digest == record.content_digest
    assert planning_digest(loaded.plan) == planning_digest(record.plan)
    assert repo.resolve_branch_head("main").revision_id == record.revision_id
    assert repo.list_revisions()[0].revision_id == record.revision_id
    assert (tmp_path / "novel/authoring/story_engine/planning/demo_001/revisions"
            / f"{record.revision_id}.json").is_file()


def test_revision_files_are_immutable(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    before = repo.revision_path(first.revision_id).read_bytes()
    second = repo.create(_plan(logline="第二版"), status="proposed")
    assert second.revision == 2
    assert second.parent_revision_id == first.revision_id
    assert repo.revision_path(first.revision_id).read_bytes() == before
    with pytest.raises(PlanningRepositoryError) as error:
        repo.create(_plan(), revision_id=first.revision_id)
    assert error.value.code == "PLANNING_REVISION_IMMUTABLE"
    assert repo.load(first.revision_id).status == "proposed"


def test_planning_id_is_stable_across_revisions(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(planning_id=""))
    assert first.planning_id.startswith("PLAN_")
    second = repo.create(_plan(planning_id=""), revision_id="")
    assert second.planning_id == first.planning_id
    with pytest.raises(PlanningRepositoryError) as error:
        repo.create(_plan(planning_id="PLAN_OTHER"))
    assert error.value.code == "PLANNING_ID_MISMATCH"


def test_branch_head_and_isolation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    repo.create_branch("experiment-a", from_revision_id=first.revision_id)
    assert repo.list_branches() == {"main": first.revision_id,
                                    "experiment-a": first.revision_id}
    experiment = repo.create(_plan(logline="实验线"), branch_id="experiment-a")
    main = repo.create(_plan(logline="主线"), status="proposed")
    assert repo.resolve_branch_head("experiment-a").revision_id == experiment.revision_id
    assert repo.resolve_branch_head("main").revision_id == main.revision_id
    assert [row.revision_id for row in repo.list_revisions(branch_id="experiment-a")] \
        == [first.revision_id, experiment.revision_id]
    assert main.parent_revision_id == first.revision_id
    assert experiment.parent_revision_id == first.revision_id
    with pytest.raises(PlanningRepositoryError) as error:
        repo.create_branch("experiment-a", from_revision_id=first.revision_id)
    assert error.value.code == "PLANNING_BRANCH_EXISTS"


def test_route_candidate_cannot_be_registered_as_planning_branch(tmp_path: Path) -> None:
    """裁决 6（硬规则）：Route Lab candidate 不是 Planning branch。"""

    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    with pytest.raises(PlanningRepositoryError) as error:
        repo.create_branch("route-b", from_revision_id=first.revision_id,
                           source_kind="route_candidate")
    assert error.value.code == "ROUTE_CANDIDATE_IS_NOT_PLANNING_BRANCH"
    assert "route-b" not in repo.list_branches()


def test_rollback_creates_new_revision_and_marks_superseded(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    second = repo.create(_plan(logline="被放弃"), status="proposed")
    rolled = repo.rollback_head(first.revision_id, branch_id="main", note="回到初稿")
    assert rolled.revision == 3
    assert rolled.status == "rolled_back"
    assert rolled.parent_revision_id == second.revision_id
    assert rolled.source_revision == first.revision_id
    assert planning_digest(rolled.plan) == planning_digest(first.plan)
    assert repo.load(second.revision_id).status == "superseded"
    assert repo.load(first.revision_id).status == "proposed"
    assert repo.resolve_branch_head("main").revision_id == rolled.revision_id
    assert [row.revision for row in repo.lineage(rolled.revision_id)] == [1, 2, 3]


def test_promote_creates_confirmed_revision_on_target_branch(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    promoted = repo.promote_revision(first.revision_id, target_branch="release",
                                     note="作者确认")
    assert promoted.status == "confirmed"
    assert promoted.branch_id == "release"
    assert promoted.source_revision == first.revision_id
    assert repo.resolve_branch_head("main").revision_id == first.revision_id
    assert repo.list_branches()["release"] == promoted.revision_id


def test_structured_diff_reports_domain_and_change_kind(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    raw = _raw()
    raw["plot_nodes"][1]["conflict"] = "改过的冲突"
    raw["volumes"][0]["title"] = "改过的卷名"
    raw["plot_nodes"].append({"node_id": "NODE_NEW", "purpose": "新增节点",
                              "conflict": "新冲突", "payoff": "新回收"})
    second = repo.create(validate_planning_ir(raw), status="proposed")
    diff = repo.compare(first.revision_id, second.revision_id)
    assert {row.change for row in diff.rows} == {"added", "modified"}
    assert {"plot", "volume"} <= set(diff.domains())
    assert any(row.change == "added" and row.domain == "plot" for row in diff.rows)
    assert all(row.path and row.domain for row in diff.rows)
    # 删除也能被识别
    raw = _raw()
    raw["foreshadow_plans"] = []
    third = repo.create(validate_planning_ir(raw), status="proposed")
    removed = repo.compare(second.revision_id, third.revision_id)
    assert any(row.change == "removed" and row.domain == "foreshadow" for row in removed.rows)


def test_supplied_overwrite_is_a_conflict_not_a_silent_choice(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    raw = _raw()
    raw["characters"][0]["external_goal"] = "生成器想改写的目标"
    raw["characters"][0]["provenance"] = "generated"
    patch = validate_planning_ir(raw)
    preview: PlanningConflict = repo.conflicts_for(repo.load(first.revision_id), patch)
    assert [item.stable_id for item in preview.items] == ["CHAR_LIN"]
    assert preview.items[0].base_provenance == "supplied"
    assert preview.items[0].incoming_provenance == "generated"
    assert len(repo.list_revisions()) == 1  # 预览不写文件
    with pytest.raises(PlanningConflictError) as error:
        repo.revise(first.revision_id, patch)
    assert error.value.conflict.items[0].stable_id == "CHAR_LIN"
    assert len(repo.list_revisions()) == 1
    preserved = repo.revise(first.revision_id, patch, on_conflict="preserve")
    assert preserved.plan.characters[0].external_goal == first.plan.characters[0].external_goal
    assert preserved.plan.characters[0].provenance == "supplied"


def test_digest_detects_tampering_and_ignores_key_order(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    record = repo.create(_plan(), status="proposed")
    assert repo.verify_digest(record.revision_id) == record.content_digest
    reordered = json.loads(json.dumps(_raw(), sort_keys=True))
    reordered = {key: reordered[key] for key in reversed(list(reordered))}
    assert planning_digest(validate_planning_ir(reordered)) \
        == planning_digest(validate_planning_ir(_raw()))
    path = repo.revision_path(record.revision_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["revision"]["plan"]["logline"] = "被手改过的内容"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PlanningRepositoryError) as error:
        repo.verify_digest(record.revision_id)
    assert error.value.code == "PLANNING_CONTENT_DIGEST_MISMATCH"


def test_repository_never_touches_canon_or_story_state(tmp_path: Path) -> None:
    """Planning persistence 只保存 Planning truth。"""

    repo = _repo(tmp_path)
    first = repo.create(_plan(), status="proposed")
    repo.create(_plan(logline="第二版"), status="proposed")
    repo.rollback_head(first.revision_id)
    written = sorted(str(path.relative_to(tmp_path)).replace("\\", "/")
                     for path in tmp_path.rglob("*") if path.is_file())
    assert written
    for path in written:
        assert path.startswith("novel/authoring/story_engine/planning/demo_001/")
