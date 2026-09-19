"""V4.0.2 PB-1 回归：历史（已解决 / 已被最新报告取代）的 issue 不得永久阻塞交付。

Dogfood 复现（`docs/v4/V4_0_1_SKILL_DOGFOOD_REPORT.md` §8 PB-1）：

```text
缺陷 → evaluate → Q9/Q8 blocker 入库
     → 修好 → 重新 evaluate（最新报告已通过）
     → verify 把历史 issue 标为 resolved
     → delivery preflight 仍然 blocked（错误；只能靠 explicit_revisions 绕开）
```

正确语义（`docs/v4/V4_DELIVERY_CONTRACT.md` §11–§13、§18）：
preflight 回答的是"**当前要交付的 Blueprint 现在是否仍有阻塞问题**"，
而不是"这个作品历史上是否出现过阻塞问题"。

本文件用公开 Application API 走完整链路（不 mock 内部 helper）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novelforge.application.services import ExportService
from novelforge.delivery import DeliveryPolicy

from delivery_support import delivery_stack

PLACEHOLDER = "TODO"
NODE_ID = "sc_001_02"


def _selection(root: Path, novel_id: str, **kwargs: Any) -> Any:
    defaults: dict[str, Any] = {"formats": ("json",)}
    defaults.update(kwargs)
    return ExportService(root, novel_id).delivery_selection(**defaults)


def _codes(payload: dict[str, Any]) -> set[str]:
    return {str(row["code"]) for row in payload["validation"]["issues"]}


def _patch_and_accept(stack: dict[str, Any], node_id: str,
                      changes: dict[str, Any]) -> None:
    """用公开 Editor API 改字段，并把新 revision 接受（模拟作者操作）。"""

    repository = stack["repository"]
    stack["service"].patch(node_id, changes,
                           expected_revision=repository.current_revision(node_id))
    repository.set_status(node_id, "accepted",
                          expected_revision=repository.current_revision(node_id))


def _scene_purpose(stack: dict[str, Any], node_id: str = NODE_ID) -> str:
    payload = stack["repository"].get_current(node_id).payload
    return str(payload.model_dump(mode="json").get("scene_purpose") or "")


def _introduce_defect(stack: dict[str, Any]) -> tuple[str, Any]:
    """造一个真实缺陷（场景卡含占位内容）→ 产生 Q8 + Q9 blocker。"""

    good = _scene_purpose(stack)
    _patch_and_accept(stack, NODE_ID,
                      {"scene_purpose": f"{PLACEHOLDER}：待补写的场景目的"})
    before = stack["quality"].evaluate()
    codes = {row.code for row in before.issues}
    assert "BLUEPRINT_PLACEHOLDER_TEXT" in codes, sorted(codes)
    assert "DELIVERY_PLACEHOLDER" in codes, sorted(codes)
    return good, before


def _fix_defect(stack: dict[str, Any], good: str) -> Any:
    """把缺陷改回去并重新评估（最新报告不再包含该问题）。"""

    _patch_and_accept(stack, NODE_ID, {"scene_purpose": good})
    after = stack["quality"].evaluate()
    assert after.status == "passed", [row.code for row in after.issues]
    return after


def test_placeholder_defect_blocks_while_it_is_current(tmp_path: Path) -> None:
    """反面守卫（§16）：问题**仍然存在**时必须继续阻塞。"""

    stack = delivery_stack(tmp_path)
    _introduce_defect(stack)
    payload = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    codes = _codes(payload)
    assert payload["validation"]["ok"] is False
    assert "DELIVERY_PLACEHOLDER_CONTENT" in codes, sorted(codes)
    assert "DELIVERY_Q9_BLOCKER" in codes, sorted(codes)


def test_resolved_historical_issue_does_not_block_delivery(tmp_path: Path) -> None:
    """PB-1 主复现：修好 + 重新评估 + verify(resolved) → 默认 preflight 必须 PASS。"""

    stack = delivery_stack(tmp_path)
    good, before = _introduce_defect(stack)
    blocking = [row.issue_id for row in before.issues
                if row.code in ("DELIVERY_PLACEHOLDER", "BLUEPRINT_PLACEHOLDER_TEXT")]
    assert blocking

    # 缺陷仍在时默认 preflight 必须被拦住（证明这个 fixture 真的会触发 blocker）
    blocked = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    assert blocked["validation"]["ok"] is False
    assert "DELIVERY_PLACEHOLDER_CONTENT" in _codes(blocked)

    after = _fix_defect(stack, good)
    verification = stack["review"].verify_repair(before_report=before,
                                                issue_ids=blocking)
    assert set(verification.resolved_issue_ids) >= set(blocking), \
        (verification.status, verification.resolved_issue_ids,
         verification.remaining_issue_ids)
    assert after.status == "passed"

    payload = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    assert payload["validation"]["ok"] is True, payload["validation"]["issues"]
    assert _codes(payload) == set()


def test_superseded_issue_from_older_report_does_not_block(tmp_path: Path) -> None:
    """不依赖 verify：单靠"最新报告不再包含该 issue"也必须解除阻塞。"""

    stack = delivery_stack(tmp_path)
    good, _before = _introduce_defect(stack)
    _fix_defect(stack, good)
    payload = stack["delivery"].validate(_selection(tmp_path, stack["novel_id"]))
    assert payload["validation"]["ok"] is True, payload["validation"]["issues"]


def test_live_q9_blocker_still_blocks_after_relaxing_policy(tmp_path: Path) -> None:
    """§16：放宽 policy 不能放过**当前**仍存在的占位内容。"""

    stack = delivery_stack(tmp_path)
    _introduce_defect(stack)
    selection = _selection(tmp_path, stack["novel_id"],
                           policy=DeliveryPolicy.relaxed())
    payload = stack["delivery"].validate(selection)
    assert payload["validation"]["ok"] is False
    assert "DELIVERY_PLACEHOLDER_CONTENT" in _codes(payload)
