"""V4-07 §16–§18、§50–§51、§76、§80：DeliveryValidator（preflight）。"""

from __future__ import annotations

from pathlib import Path

from novelforge.application.services import ExportService
from novelforge.delivery import DeliveryPolicy, DeliverySelection

from delivery_support import delivery_stack, editor_stack


def _selection(root: Path, novel_id: str, **kwargs) -> DeliverySelection:
    defaults = {"formats": ("json",)}
    defaults.update(kwargs)
    return ExportService(root, novel_id).delivery_selection(**defaults)


def test_clean_accepted_novel_passes_preflight(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    payload = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    assert payload["validation"]["ok"] is True
    assert payload["validation"]["issues"] == []
    assert payload["validation"]["quality_summary"]["nodes"] == \
        len(payload["snapshot"]["node_revisions"])


def test_no_accepted_revision_blocks_delivery(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path, clean=False)
    payload = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert {"DELIVERY_NO_ACCEPTED_REVISION", "DELIVERY_MISSING_REQUIRED_NODE"} & codes
    assert payload["validation"]["ok"] is False
    assert payload["validation"]["blocking_reason"]


def test_accepted_and_quality_requirements_are_independent(tmp_path: Path) -> None:
    """§11：accepted 与 quality 是两个独立要求，不能互相替代。"""

    stack = delivery_stack(tmp_path)
    accepted_only = _selection(
        tmp_path, stack["novel_id"],
        policy=DeliveryPolicy(require_accepted=True, require_quality_pass=False))
    assert stack["delivery"].validate(accepted_only)["validation"]["ok"] is True


def test_stale_quality_is_detected(tmp_path: Path) -> None:
    """§76：r3 评估通过 → 编辑成 r4（未评估）→ current + require_quality_pass 失败。"""

    stack = delivery_stack(tmp_path)
    evaluated = stack["repository"].current_revision("sc_001_02")
    # 在评估过的 revision 之上再编辑一次 → 新 revision 没有质量结论
    stack["repository"].save_revision(
        stack["repository"].get_current("sc_001_02"), expected_revision=evaluated)
    payload = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"], selection_mode="current",
        policy=DeliveryPolicy(require_accepted=False, require_quality_pass=True,
                              allow_unevaluated=True)))
    rows = {row["code"]: row for row in payload["validation"]["issues"]}
    assert "DELIVERY_QUALITY_STALE" in rows
    assert rows["DELIVERY_QUALITY_STALE"]["node_ids"] == ["sc_001_02"]
    assert payload["validation"]["ok"] is False
    relaxed = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"], selection_mode="current",
        policy=DeliveryPolicy(require_accepted=False, require_quality_pass=True,
                              allow_unevaluated=True, allow_stale_quality=True)))
    assert relaxed["validation"]["ok"] is True
    assert any(row["code"] == "DELIVERY_QUALITY_STALE"
               for row in relaxed["validation"]["warnings"])


def test_unevaluated_node_blocks_when_policy_requires_quality(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    stack["repository"].save_revision(
        stack["repository"].get_current("sc_001_02"),
        expected_revision=stack["repository"].current_revision("sc_001_02"))
    payload = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"], selection_mode="current",
        policy=DeliveryPolicy(require_accepted=False)))
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert codes & {"DELIVERY_QUALITY_UNEVALUATED", "DELIVERY_QUALITY_STALE"}


def test_quality_failure_is_reported_with_blocking_codes(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path, clean=False)
    # 用 current 模式 + 放宽 accepted，但保留质量要求（未评估 → blocker）
    payload = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"], selection_mode="current",
        policy=DeliveryPolicy(require_accepted=False, require_quality_pass=True)))
    assert payload["validation"]["ok"] is False
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert "DELIVERY_QUALITY_UNEVALUATED" in codes


def test_q9_issues_are_reused_not_reimplemented(tmp_path: Path) -> None:
    """§18：DeliveryValidator 复用 Quality Store 的 Q9 结论。"""

    stack = delivery_stack(tmp_path, clean=False, repairable=False)
    report = stack["quality"].evaluate(gates=("Q9",))
    q9 = [row for row in report.issues if row.gate == "Q9"]
    assert q9, "fixture 应当产生 Q9 交付就绪度问题"
    payload = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"], selection_mode="current",
        policy=DeliveryPolicy(require_accepted=False, require_quality_pass=False,
                              allow_unevaluated=True)))
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert "DELIVERY_Q9_BLOCKER" in codes
    row = [item for item in payload["validation"]["issues"]
           if item["code"] == "DELIVERY_Q9_BLOCKER"][0]
    assert row["evidence"]["quality_code"].startswith("DELIVERY_")


def test_missing_required_node_and_orphan_detection(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = _selection(tmp_path, stack["novel_id"],
                           include_node_types=("scene",),
                           policy=DeliveryPolicy.relaxed())
    payload = stack["delivery"].validate(selection)
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert "DELIVERY_MISSING_REQUIRED_NODE" in codes
    assert "DELIVERY_ORPHAN_NODE" in codes or "DELIVERY_REFERENCE_BROKEN" in codes


def test_cross_novel_contamination_is_blocker(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = _selection(tmp_path, stack["novel_id"],
                           selection_mode="explicit_revisions",
                           explicit_revisions={"sc_001_02": 1})
    outcome = stack["delivery"].selector.select(selection)
    # 人为把 foreign 节点放进 outcome → 校验必须报跨作品
    from novelforge.delivery.selection import SelectionOutcome

    from dataclasses import replace

    foreign = {**dict(outcome.selected), "foreign_node": 1}
    snapshot = stack["delivery"]._build_snapshot(  # noqa: SLF001 - 构造污染场景
        selection, SelectionOutcome(selection=selection, selected=foreign,
                                    node_types={**dict(outcome.node_types),
                                                "foreign_node": "scene"}))
    validation = stack["delivery"].validator.preflight(
        selection=selection, outcome=SelectionOutcome(selection=selection,
                                                     selected=foreign),
        snapshot=snapshot)
    codes = {row.code for row in validation.issues}
    assert "DELIVERY_REVISION_MISSING" in codes


def test_invalidation_pending_is_detected(tmp_path: Path) -> None:
    """§14：质量评估之后又发生编辑 → 交付前必须重新评估。"""

    stack = delivery_stack(tmp_path)
    node_id = "sc_001_02"
    stack["quality"].evaluate()          # 评估（记录 accepted revision）
    stack["service"].patch(node_id, {"next_hook": "评估之后又改了一次"},
                           expected_revision=stack["repository"].current_revision(node_id))
    stack["repository"].set_status(node_id, "accepted",
                                   expected_revision=stack["repository"].current_revision(
                                       node_id))
    payload = stack["delivery"].validate(_selection(
        tmp_path, stack["novel_id"],
        policy=DeliveryPolicy(require_quality_pass=False)))
    codes = {row["code"] for row in payload["validation"]["issues"]}
    assert "DELIVERY_INVALIDATION_PENDING" in codes
