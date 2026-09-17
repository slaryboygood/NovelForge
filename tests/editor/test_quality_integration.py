"""V4-06 §28–§33、§57、§77：Editor × Quality（issue 归属 revision、repair preview、
repair / verify、编辑后质量失效、Golden Editor Workflow）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from editor_support import (
    current_payload,
    editor_stack,
    repaired_chapter_payload,
    repaired_scene_payload,
    revision,
    scripted,
)


def _evaluated_stack(tmp_path: Path, **kwargs) -> dict:
    stack = editor_stack(tmp_path, **kwargs)
    stack["service"].evaluate("sc_001_02")
    return stack


def test_current_revision_issues_are_visible(tmp_path: Path) -> None:
    stack = _evaluated_stack(tmp_path)
    quality = stack["service"].get_quality("sc_001_02")
    assert quality["requested_revision"] == 1
    assert quality["issues"] and quality["historical_issues"] == []
    assert {row["code"] for row in quality["issues"]} >= {
        "SCENE_NO_NARRATIVE_FUNCTION"}
    assert quality["blocking_codes"]


def test_old_revision_issues_are_marked_historical(tmp_path: Path) -> None:
    """§29：r1 的 issue 不能显示成 r2 的当前问题。"""

    stack = _evaluated_stack(tmp_path)
    stack["service"].patch("sc_001_02", {"story_function": ["advance_plot", "decision"]},
                           expected_revision=1)
    quality = stack["service"].get_quality("sc_001_02")
    assert quality["requested_revision"] == 2
    assert quality["issues"] == []
    assert quality["historical_issues"]
    assert all(row["historical"] is True for row in quality["historical_issues"])
    assert all(row["revision"] == 1 for row in quality["historical_issues"])
    assert "旧 revision" in quality["note"]


def test_edit_invalidates_quality_status(tmp_path: Path) -> None:
    """§31：手工编辑后 quality_status = unevaluated（不得沿用旧的 passed）。"""

    stack = _evaluated_stack(tmp_path)
    node = stack["repository"].get_current("sc_001_02")
    assert node.quality_status == "unevaluated"
    stack["repository"].set_status("sc_001_02", "draft", expected_revision=1)
    stack["service"].patch("sc_001_02", {"turn": "新的转折"}, expected_revision=2)
    current = stack["repository"].get_current("sc_001_02")
    assert current.quality_status == "unevaluated"
    assert current.status == "proposed"


def test_repair_preview_explains_scope_and_gates(tmp_path: Path) -> None:
    """§30：问题是什么 / 改哪些节点 / 允许改什么 / 保留什么 / 复核哪些 gate。"""

    stack = _evaluated_stack(tmp_path)
    preview = stack["service"].plan_repair(node_id="sc_001_02")
    assert preview["status"] == "planned" and preview["dry_run"] is True
    assert preview["preview"]["target_nodes"] == ["sc_001_02"]
    assert "story_function" in preview["preview"]["allowed_fields"]
    assert "chapter_id" in preview["preview"]["preserve_fields"]
    assert "Q7" in preview["preview"]["verification_gates"]
    assert preview["preview"]["estimated_model_calls"] == 1
    assert revision(stack, "sc_001_02") == 1        # preview 不写 revision
    assert stack["provider"].calls == 0


def test_repair_execution_and_verification(tmp_path: Path) -> None:
    """§57 的一条真实 workflow：issue → plan → repair → verify。"""

    stack = editor_stack(tmp_path, repairable=True)
    stack["service"].evaluate("sc_001_02")
    quality = stack["service"].get_quality("sc_001_02")
    issue_ids = [row["issue_id"] for row in quality["issues"]]
    assert issue_ids
    scripted(stack, repaired_scene_payload(sequence=1))
    outcome = stack["service"].repair(issue_ids)
    assert outcome["plan"]["status"] == "planned"
    assert outcome["result"]["status"] == "applied"
    assert outcome["verification"]["status"] in ("resolved", "partial")
    assert revision(stack, "sc_001_02") == 2
    # repair 也进入 editor 审计（§47）
    operations = stack["service"].operations(node_id="sc_001_02")
    assert any(row["operation"] == "quality_repair" for row in operations)


def test_golden_editor_workflow(tmp_path: Path) -> None:
    """§77：generate → evaluate → issue → repair preview → repair → diff → verify
    → accept → manual edit → quality invalidated → restore。"""

    stack = editor_stack(tmp_path, repairable=True)
    service = stack["service"]

    # 1) 质量评估 → 发现 issue
    report = service.evaluate("sc_001_02")
    assert report["status"] != "passed" and report["issues"]
    issue_ids = list(report["issues_for_node"])
    assert issue_ids

    # 2) repair preview（dry run，不写 revision）
    preview = service.plan_repair(node_id="sc_001_02")
    assert preview["status"] == "planned"
    assert revision(stack, "sc_001_02") == 1

    # 3) 执行 repair → 新 revision（proposed）
    scripted(stack, repaired_scene_payload(sequence=1))
    outcome = service.repair(issue_ids)
    assert outcome["result"]["status"] == "applied"
    assert revision(stack, "sc_001_02") == 2
    assert stack["repository"].get_current("sc_001_02").status == "proposed"

    # 4) diff r1 → r2
    diff = service.diff("sc_001_02", from_revision=1, to_revision=2)
    assert diff["changed"] is True
    assert "story_function" in diff["all_changed_fields"]
    assert diff["quality"]["resolved_issue_ids"] or diff["quality"]["before_issue_ids"]

    # 5) verify（重新评估）
    verification = service.verify_repair(issue_ids=issue_ids)
    assert verification["status"] in ("resolved", "partial")

    # 6) accept（作者决定，与质量结论独立）
    accepted = service.accept("sc_001_02", expected_revision=2, reason="采用修复结果")
    assert accepted["status"] == "applied"
    assert stack["repository"].get_current("sc_001_02").status == "accepted"

    # 7) 手工编辑 → 质量失效（新 revision 不是 accepted）
    edited = service.patch("sc_001_02", {"next_hook": "作者补的钩子"},
                           expected_revision=revision(stack, "sc_001_02"))
    assert edited["status"] == "applied"
    current = stack["repository"].get_current("sc_001_02")
    assert current.status == "proposed"
    assert current.quality_status == "unevaluated"
    assert stack["repository"].get_revision("sc_001_02", 3).status == "accepted"

    # 8) restore 到修复后的那一版（历史全部保留）
    final_revision = revision(stack, "sc_001_02")
    restored = service.restore("sc_001_02", from_revision=2,
                               expected_revision=final_revision)
    assert restored["status"] == "applied"
    assert stack["repository"].list_revisions("sc_001_02") == \
        [1, 2, 3, 4, 5]
    assert stack["repository"].get_current("sc_001_02").payload.next_hook != \
        "作者补的钩子"


def test_quality_issue_scope_matches_edited_node_only(tmp_path: Path) -> None:
    stack = _evaluated_stack(tmp_path)
    other = stack["service"].get_quality("ch_001")
    assert other["issues"] == [] or all(
        row["scope"]["node_ids"] == ["ch_001"] for row in other["issues"])


def test_evaluate_and_repair_loop_through_editor(tmp_path: Path) -> None:
    stack = editor_stack(tmp_path, repairable=True)
    scripted(stack, repaired_scene_payload(sequence=1), repaired_chapter_payload())
    payload = current_payload(stack, "sc_001_02")
    scripted(stack, {**payload, "story_function": ["advance_plot", "decision"]},
             repaired_chapter_payload())
    loop = stack["service"].evaluate_and_repair(node_id="sc_001_02")
    assert loop["status"] in ("passed", "repaired", "needs_human_review")
    assert loop["rounds"] <= 3
