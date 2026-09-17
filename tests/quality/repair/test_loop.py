"""V4-05 §56–§58、§63–§66：Quality Closed Loop（Evaluate → Plan → Repair → Verify）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.quality import QualityPolicy

from quality_support import (
    NOVEL_ID,
    quality_stack,
    repaired_chapter_payload,
    repaired_scene_payload,
)


def _script() -> list[object]:
    return [repaired_chapter_payload(), repaired_scene_payload(sequence=1),
            repaired_scene_payload(sequence=2), repaired_scene_payload(sequence=3)]


def test_golden_closed_loop_reaches_passed(tmp_path: Path) -> None:
    """§63：issue → plan → dry-run → execute → new revision → verify → resolved。"""

    stack = quality_stack(tmp_path, script=_script(), repairable=True)
    review = stack["review"]
    before = {node.node_id: node for node in stack["repository"].all_nodes()}

    plan = review.evaluate_and_repair(dry_run=True)
    assert plan.status == "planned"
    assert plan.plans[0].estimated_model_calls == 4
    assert stack["provider"].calls == 0

    loop = review.evaluate_and_repair()
    assert loop.status == "passed"
    assert loop.needs_human_review is False
    assert loop.rounds == 1
    assert loop.verification is not None
    assert loop.verification.status == "resolved"
    assert not loop.report.issues
    assert loop.report.status == "passed"
    assert stack["provider"].calls == 4

    # §64：计划外的节点 byte-for-byte（canonical serialized form）不变
    after = {node.node_id: node for node in stack["repository"].all_nodes()}
    target_nodes = set(loop.plans[0].target_node_ids)
    for node_id, node in before.items():
        if node_id in target_nodes:
            continue
        assert after[node_id].as_dict() == node.as_dict(), node_id

    # usage 汇总（§41）
    assert loop.usage["repair"]["calls"] == 4
    assert loop.usage["repair"]["input_tokens"] > 0
    assert loop.usage["total"]["calls"] == loop.usage["repair"]["calls"]


def test_loop_reports_needs_human_review_for_non_repairable_issue(
        tmp_path: Path) -> None:
    """§57：未回收 setup 无法通过重生成场景解决 → 必须上报人工决定。"""

    stack = quality_stack(tmp_path, script=_script() + [
        repaired_scene_payload(sequence=2)], repairable=False)
    loop = stack["review"].evaluate_and_repair(max_rounds=2)
    assert loop.status == "needs_human_review"
    assert loop.needs_human_review is True
    assert loop.rounds <= 2
    assert loop.reasons
    assert "DELIVERY_UNPAID_SETUP" in " ".join(loop.reasons) or \
        "没有解决任何 issue" in " ".join(loop.reasons)


def test_loop_returns_repaired_when_targets_are_resolved(tmp_path: Path) -> None:
    """目标 issue 全部解决即视为完成；剩余 blocking issue 仍需人工关注。"""

    stack = quality_stack(tmp_path, script=_script(), repairable=False)
    report = stack["review"].evaluate()
    targets = [row.issue_id for row in report.issues
               if row.code not in ("DELIVERY_UNPAID_SETUP", "DEAD_BRANCH")]
    loop = stack["review"].evaluate_and_repair(issue_ids=targets)
    assert loop.status == "repaired"
    assert loop.verification.status == "resolved"
    assert loop.needs_human_review is True
    assert any("未解决的 blocking issue" in reason for reason in loop.reasons)


def test_loop_honours_max_rounds_and_budget(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=_script(), repairable=True)
    zero = stack["review"].evaluate_and_repair(max_rounds=0)
    assert zero.status == "needs_human_review"
    assert "max_repair_rounds=0" in " ".join(zero.reasons)

    survivor = dict(repaired_scene_payload(sequence=3))
    survivor["character_goals"] = []
    survivor["escalation"] = ""
    survivor["conflict"] = ""
    tight = quality_stack(tmp_path / "budget", script=[survivor], repairable=True)
    loop = tight["review"].evaluate_and_repair(
        issue_ids=[row.issue_id for row in tight["review"].evaluate().issues
                   if row.scope.node_ids == ("sc_001_04",)],
        policy=QualityPolicy(required_gates=("Q4", "Q5"), token_limit=1))
    assert loop.status == "needs_human_review"
    assert any("token budget" in reason for reason in loop.reasons)


def test_loop_uses_blast_radius_not_full_blueprint(tmp_path: Path) -> None:
    stack = quality_stack(tmp_path, script=_script(), repairable=True)
    loop = stack["review"].evaluate_and_repair()
    assert loop.verification is not None
    # 复核范围 = blast radius（direct + dependent），不是全部节点
    assert set(loop.verification.after_revisions) <= set(
        loop.plans[0].blast_radius.scope)
    assert loop.report.scope.kind == "changed"


def test_review_service_exposes_mcp_friendly_surface(tmp_path: Path) -> None:
    """§55 / §73：Application Service 是接口层的唯一入口（形状适合未来 MCP）。"""

    stack = quality_stack(tmp_path, script=_script(), repairable=True)
    review = stack["review"]
    report = review.evaluate()
    assert report.novel_id == NOVEL_ID
    issues = review.list_issues(status="open")
    assert issues and {"issue_id", "code", "gate", "severity", "scope"} <= set(issues[0])
    plan = review.plan_repair(dry_run=True)
    outcome = review.repair_issue([row["issue_id"] for row in issues],
                                  before_report=report, dry_run=True)
    assert outcome.status == "planned"
    assert outcome.as_dict()["plan"]["dry_run"] is True
    assert plan.as_dict()["estimated_model_calls"] >= 1
