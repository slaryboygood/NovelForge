"""V4-07 §7–§14、§69、§74–§75：revision 选择（accepted / explicit / current）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from novelforge.application.services import ExportService
from novelforge.delivery import DeliveryPolicy, DeliverySelection
from novelforge.delivery.errors import DeliveryOwnershipError, DeliverySelectionError

from delivery_support import delivery_stack


def _selection(stack: dict, **kwargs) -> DeliverySelection:
    defaults = {"formats": ("json",)}
    defaults.update(kwargs)
    return ExportService(stack["root"], stack["novel_id"]).delivery_selection(**defaults)


def test_accepted_selection_picks_accepted_revision(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    outcome = stack["delivery"].selector.select(_selection(stack))
    for node_id, revision in outcome.selected.items():
        stored = stack["repository"].get_revision(node_id, revision)
        assert str(stored.status) == "accepted"
    assert not outcome.excluded


def test_proposed_revision_is_excluded(tmp_path: Path) -> None:
    """§74：r3 accepted / r4 proposed → 必须导出 r3，不得出现 r4 独有文本。"""

    stack = delivery_stack(tmp_path)
    accepted_revision = stack["repository"].current_revision("sc_001_02")
    stack["service"].patch("sc_001_02", {"turn": "PROPOSED-ONLY-MARKER"},
                           expected_revision=accepted_revision)
    assert stack["repository"].current_revision("sc_001_02") == accepted_revision + 1
    outcome = stack["delivery"].selector.select(_selection(stack))
    assert outcome.selected["sc_001_02"] == accepted_revision
    result = stack["delivery"].deliver(__import__(
        "novelforge.delivery", fromlist=["DeliveryRequest"]).DeliveryRequest(
            selection=_selection(stack, formats=("json", "markdown"))))
    blob = b"".join(artifact.content for artifact in result.artifacts)
    assert b"PROPOSED-ONLY-MARKER" not in blob


def test_rejected_revision_is_not_delivered(tmp_path: Path) -> None:
    """§75：被 rejected 的 revision 不得进入正式交付内容。"""

    stack = delivery_stack(tmp_path)
    current = stack["repository"].current_revision("ch_001")
    stack["service"].reject("ch_001", revision=current, reason="不满意")
    outcome = stack["delivery"].selector.select(_selection(stack))
    assert "ch_001" not in outcome.selected
    assert any(row["node_id"] == "ch_001" and
               row["reason"] == "NO_ACCEPTED_REVISION" for row in outcome.excluded)
    assert outcome.review_refs.get("ch_001") in (None, "")


def test_explicit_revision_selection(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = _selection(stack, selection_mode="explicit_revisions",
                           explicit_revisions={"sc_001_02": 1},
                           policy=DeliveryPolicy.relaxed(),
                           formats=("json",))
    outcome = stack["delivery"].selector.select(selection)
    assert outcome.selected == {"sc_001_02": 1}
    assert outcome.excluded
    bad = _selection(stack, selection_mode="explicit_revisions",
                     explicit_revisions={"sc_001_02": 99})
    with pytest.raises(DeliverySelectionError):
        stack["delivery"].selector.select(bad)


def test_current_selection_is_allowed_but_marked_by_policy(tmp_path: Path) -> None:
    """§8：current 有明确风险策略 —— 默认 policy 会因未 accepted 而阻断。"""

    stack = delivery_stack(tmp_path, clean=False)
    selection = _selection(stack, selection_mode="current", formats=("json",))
    assert stack["delivery"].selector.select(selection).selected["ch_001"] == 1
    blocked = stack["delivery"].deliver(__import__(
        "novelforge.delivery", fromlist=["DeliveryRequest"]).DeliveryRequest(
            selection=selection))
    codes = {issue.code for issue in blocked.validation.issues}
    assert "DELIVERY_NO_ACCEPTED_REVISION" in codes
    relaxed = _selection(stack, selection_mode="current", policy=DeliveryPolicy.relaxed(),
                         formats=("json",))
    described = stack["delivery"].describe(relaxed)
    assert described["selection_outcome"]["selected"]


def test_include_node_types_filter(tmp_path: Path) -> None:
    stack = delivery_stack(tmp_path)
    selection = _selection(stack, include_node_types=("premise", "theme"),
                           policy=DeliveryPolicy.relaxed())
    outcome = stack["delivery"].selector.select(selection)
    assert set(outcome.node_types.values()) == {"premise", "theme"}
    assert any(row["reason"] == "NODE_TYPE_FILTERED" for row in outcome.excluded)


def test_selection_is_novel_isolated(tmp_path: Path) -> None:
    """§68–§69：A 的交付不含 B 的任何数据（即使 node_id 相同）。"""

    from delivery_support import editor_stack

    stack = delivery_stack(tmp_path)
    other = editor_stack(tmp_path, novel_id="novel_beta", repairable=True,
                         script=[])
    alpha_ids = set(stack["delivery"].selector.select(_selection(stack)).selected)
    beta_ids = {node.node_id for node in other["repository"].all_nodes()}
    assert alpha_ids & beta_ids           # 两本作品 node_id 完全相同
    # alpha 的 storage 只包含 alpha 的节点（同 id 也不会读到 beta 的内容）
    beta_revision = other["repository"].current_revision("ch_001")
    assert stack["repository"].current_revision("ch_001") >= 1
    assert stack["repository"].get_revision("ch_001", beta_revision) is not None
    # 用 alpha 的 delivery service 请求 beta 的 selection → 必须拒绝
    with pytest.raises(DeliveryOwnershipError):
        stack["delivery"].selector.select(DeliverySelection(
            novel_id="novel_beta", formats=("json",)))
