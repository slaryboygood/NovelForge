"""V4-05 §33–§36、§65–§66：Targeted Repair —— 新 revision / 冲突 / 幂等 / preserve。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.core.revision import RevisionConflict

from quality_support import (
    quality_stack,
    repaired_chapter_payload,
    repaired_scene_payload,
)


def _stack(tmp_path: Path):
    script = [repaired_chapter_payload(), repaired_scene_payload(sequence=1),
              repaired_scene_payload(sequence=2), repaired_scene_payload(sequence=3)]
    return quality_stack(tmp_path, script=script, repairable=True)


def _plan(stack):
    report = stack["review"].evaluate()
    return report, stack["review"].planner.plan(report.issues, dry_run=True)


def test_dry_run_writes_nothing_and_calls_no_model(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _report, plan = _plan(stack)
    result = stack["review"].execute_repair(plan)
    assert result.status == "planned" and result.dry_run is True
    assert result.after_revisions == {}
    assert stack["provider"].calls == 0
    assert stack["repository"].current_revision("sc_001_02") == 1


def test_targeted_repair_creates_new_revisions(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    before = {node.node_id: node.revision
              for node in stack["repository"].all_nodes()}
    report, plan = _plan(stack)
    result = stack["review"].execute_repair(plan, dry_run=False)
    assert result.status == "applied"
    assert stack["provider"].calls == len(plan.steps)
    for node_id in plan.target_node_ids:
        assert result.after_revisions[node_id] == before[node_id] + 1

    # §64：未在计划内的节点保持 byte-for-byte（canonical serialized form）不变
    after = {node.node_id: node for node in stack["repository"].all_nodes()}
    for node_id, revision in before.items():
        if node_id in plan.target_node_ids:
            continue
        assert after[node_id].revision == revision
    assert stack["repository"].get_revision("sc_001_02", 1).payload.outcome == \
        "主角获得线索但失去许可"      # 旧 revision 永久可读
    assert result.as_dict()["usage"]["calls"] == len(plan.steps)


def test_accepted_revision_is_not_silently_overwritten(tmp_path: Path) -> None:
    """§36：accepted r2 → repair proposal r3；r2 仍为 accepted。"""

    stack = _stack(tmp_path)
    stack["repository"].set_status("sc_001_02", "accepted", expected_revision=1)
    assert stack["repository"].get_current("sc_001_02").revision == 2
    report = stack["review"].evaluate()
    plan = stack["review"].planner.plan(
        [row for row in report.issues if row.scope.node_ids == ("sc_001_02",)],
        dry_run=True)
    result = stack["review"].execute_repair(plan, dry_run=False)
    assert result.status == "applied"
    assert result.after_revisions["sc_001_02"] == 3
    assert stack["repository"].get_revision("sc_001_02", 2).status == "accepted"
    assert stack["repository"].get_revision("sc_001_02", 3).status == "proposed"


def test_revision_conflict_happens_before_any_model_call(tmp_path: Path) -> None:
    """§65：Planner 基于 r1，期间出现 r2 → RevisionConflict 且 0 次模型调用。"""

    stack = _stack(tmp_path)
    _report, plan = _plan(stack)
    stack["repository"].save_revision(
        stack["repository"].get_current("sc_001_02"), expected_revision=1)
    assert stack["repository"].current_revision("sc_001_02") == 2
    with pytest.raises(RevisionConflict) as exc:
        stack["review"].execute_repair(plan, dry_run=False)
    assert exc.value.artifact_id == "sc_001_02"
    assert stack["provider"].calls == 0
    assert stack["repository"].current_revision("ch_001") == 1


def test_same_idempotency_key_does_not_create_second_revision(tmp_path: Path) -> None:
    """§66：相同 idempotency_key 的重放不产生第二个 revision。"""

    stack = _stack(tmp_path)
    _report, plan = _plan(stack)
    key = f"rp-{plan.plan_id}"
    first = stack["review"].execute_repair(plan, dry_run=False,
                                           idempotency_key=key)
    calls_after_first = stack["provider"].calls
    second = stack["review"].execute_repair(plan, dry_run=False,
                                            idempotency_key=key)
    assert first.status == "applied"
    assert second.status == "idempotent_replay"
    assert len(second.replayed_steps) == len(plan.steps)
    assert stack["provider"].calls == calls_after_first
    for node_id in plan.target_node_ids:
        assert stack["repository"].current_revision(node_id) == \
            first.after_revisions[node_id]


def test_preserve_violation_is_reported_not_silently_accepted(tmp_path: Path) -> None:
    """§30：模型改写 preserve 字段（章节 characters）必须上报，不得静默接受。"""

    from novelforge.blueprint import CharacterPayload

    from quality_support import NOVEL_ID, node

    bad = repaired_chapter_payload()
    bad["characters"] = ["char_001", "char_002"]  # 合法但违反 preserve
    script = [bad, repaired_scene_payload(sequence=1),
              repaired_scene_payload(sequence=2),
              repaired_scene_payload(sequence=3)]
    extra = [node(NOVEL_ID, "char_002", "character",
                  CharacterPayload(name="对手", kind="npc",
                                   goal="阻止主角修好中转站的备用电源"),
                  parent_id="premise", sequence=2)]
    stack = quality_stack(tmp_path, script=script, repairable=True,
                          extra_nodes=extra)
    report = stack["review"].evaluate()
    plan = stack["review"].planner.plan(report.issues, dry_run=True)
    result = stack["review"].execute_repair(plan, dry_run=False)
    assert result.status in ("partial", "needs_human_review")
    blocked = [row for row in result.blocked_steps
               if row.get("error") == "REPAIR_PRESERVE_VIOLATION"]
    assert blocked and blocked[0]["fields"] == ["characters"]


def test_generation_failure_is_recorded_as_blocked_step(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=[], repairable=True)
    report = stack["review"].evaluate()
    plan = stack["review"].planner.plan(report.issues, dry_run=True)
    result = stack["review"].execute_repair(plan, dry_run=False)
    assert result.status == "needs_human_review"
    assert result.blocked_steps
    assert result.applied_steps == ()


def test_cross_novel_execution_is_refused(tmp_path: Path) -> None:
    from novelforge.quality import QualityScopeError

    stack = _stack(tmp_path)
    _report, plan = _plan(stack)
    other_plan = type(plan)(
        plan_id="RP_x", novel_id="novel_beta", scope=plan.scope, status="planned",
        steps=plan.steps, contracts=plan.contracts, blast_radius=plan.blast_radius)
    with pytest.raises(QualityScopeError):
        stack["review"].execute_repair(other_plan, dry_run=False)


def test_repair_history_is_recorded(tmp_path: Path) -> None:
    stack = _stack(tmp_path)
    _report, plan = _plan(stack)
    stack["review"].execute_repair(plan, dry_run=False)
    history = stack["quality"].store.repair_history()
    assert history and history[0]["plan"]["plan_id"] == plan.plan_id
    assert history[0]["result"]["status"] == "applied"
