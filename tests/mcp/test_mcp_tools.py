"""V4-08 §16–§27、§33–§36、§63、§65、§68：MCP Tools（生成 / 编辑 / 质量 / 交付）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.application.services import ExportService

from mcp_support import current_payload, envelope, error_code, mcp_stack, scripted


def _patch(stack: dict, **kwargs) -> dict:
    arguments = {"novel_id": "novel_alpha", "node_id": "ch_001",
                 "expected_revision": stack["repository"].current_revision("ch_001"),
                 "changes": {"hook": "新的钩子"}}
    arguments.update(kwargs)
    return envelope(stack["dispatcher"], "patch_blueprint_node", **arguments)


def _base(stack: dict, node_id: str = "ch_001") -> int:
    return stack["repository"].current_revision(node_id)


def test_tools_are_discovered_with_metadata(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    specs = {spec.name: spec for spec in stack["dispatcher"].tool_specs()}
    assert {"generate_scene_plan", "patch_blueprint_node", "rewrite_blueprint_node",
            "accept_revision", "reject_revision", "restore_revision",
            "evaluate_blueprint", "plan_repair", "repair_issue", "verify_repair",
            "validate_delivery", "create_delivery_snapshot",
            "deliver_blueprint"} <= set(specs)
    assert specs["patch_blueprint_node"].requires_revision is True
    assert specs["patch_blueprint_node"].supports_dry_run is True
    assert specs["rewrite_blueprint_node"].supports_dry_run is True
    assert specs["plan_repair"].read_only is True
    assert specs["diff_revisions"].read_only is True
    assert specs["generate_scene_plan"].expensive is True
    assert all(spec.input_schema.get("additionalProperties") is False
               for spec in specs.values())
    assert all("novel_id" in json.dumps(spec.input_schema)
               for spec in specs.values())


def test_invalid_arguments_are_rejected_strictly(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    extra = _patch(stack, unexpected_field="x")
    assert error_code(extra) == "MCP_INVALID_ARGUMENT"
    missing = envelope(stack["dispatcher"], "patch_blueprint_node",
                       novel_id="novel_alpha", node_id="ch_001")
    assert error_code(missing) == "MCP_INVALID_ARGUMENT"
    bad_type = _patch(stack, changes="not-a-dict")
    assert error_code(bad_type) == "MCP_INVALID_ARGUMENT"
    assert "Traceback" not in json.dumps(missing, ensure_ascii=False)
    assert "F:\\" not in json.dumps(missing, ensure_ascii=False)


def test_generation_tools_require_gateway(tmp_path: Path) -> None:
    """§9：MCP 不直接调模型 —— 未配置 gateway 时应用层给出 LLM_UNAVAILABLE。"""

    from novelforge.application.services.facade import application_services
    from novelforge.interfaces.mcp import create_dispatcher

    stack = mcp_stack(tmp_path)
    dispatcher = create_dispatcher(
        tmp_path, services_factory=lambda root, novel_id, **kwargs:
        application_services(root, novel_id))
    result = envelope(dispatcher, "generate_premise", novel_id="novel_alpha")
    assert error_code(result) == "MCP_LLM_UNAVAILABLE"
    assert result["errors"][0]["cause"] == "MCP_LLM_UNAVAILABLE"
    assert stack["dispatcher"] is not dispatcher


def test_generate_scene_plan_creates_proposal(tmp_path: Path) -> None:
    from mcp_support import repaired_scene_payload

    stack = mcp_stack(tmp_path, clean=False,
                      script=[repaired_scene_payload("ch_001", sequence=2)])
    result = envelope(stack["dispatcher"], "generate_scene_plan",
                      novel_id="novel_alpha", parent_id="ch_001",
                      task_input={"chapter_index": 1, "sequence": 2,
                                  "chapter_node_id": "ch_001",
                                  "task": "生成第二章场景"})
    assert result["ok"] is True, result["errors"]
    assert result["revision"] >= 1
    node = result["result"]["node"]
    assert node["status"] == "proposed"           # §21：不自动接受
    assert current_payload(stack, "ch_001")       # fixture 仍可读


def test_patch_tool_dry_run_then_apply(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    dry = _patch(stack, dry_run=True)
    assert dry["ok"] is True and dry["dry_run"] is True
    base = _base(stack)
    assert stack["repository"].current_revision("ch_001") == base
    applied = _patch(stack)
    assert applied["ok"] is True and applied["revision"] == base + 1
    assert stack["repository"].get_current("ch_001").payload.hook == "新的钩子"
    assert applied["revision_before"] == base
    assert applied["resources"] == [
        "novelforge://novels/novel_alpha/blueprint/nodes/ch_001"]


def test_patch_tool_revision_conflict_is_stable_error(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    base = _base(stack)
    _patch(stack)
    conflict = _patch(stack, expected_revision=base, changes={"hook": "又一次"})
    assert error_code(conflict) == "MCP_REVISION_CONFLICT"
    cause = conflict["errors"][0]["cause"]
    assert cause == "EDITOR_REVISION_CONFLICT"
    details = conflict["errors"][0]["details"]
    assert details["expected_revision"] == base and \
        details["actual_revision"] == base + 1
    assert "conflict_diff" in details
    assert stack["repository"].current_revision("ch_001") == base + 1


def test_patch_tool_preserve_violation(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    result = _patch(stack, node_id="sc_001_02",
                    expected_revision=stack["repository"].current_revision("sc_001_02"),
                    changes={"chapter_id": "ch_002"})
    assert error_code(result) == "MCP_PRESERVE_VIOLATION"
    assert result["errors"][0]["details"]["structural_fields"] == ["chapter_id"]


def test_patch_tool_idempotency(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    base = _base(stack)
    first = _patch(stack, idempotency_key="k-mcp-1")
    second = _patch(stack, idempotency_key="k-mcp-1")
    assert first["revision"] == second["revision"] == base + 1
    assert stack["repository"].current_revision("ch_001") == base + 1


def test_rewrite_tool_only_targets_fields(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    base = _base(stack)
    scripted(stack, {**payload, "turn": "接口改写的转折"})
    result = envelope(stack["dispatcher"], "rewrite_blueprint_node",
                      novel_id="novel_alpha", node_id="ch_001",
                      expected_revision=base,
                      target_fields=["turn"], instruction="把转折写具体",
                      preserve_fields=["characters"])
    assert result["ok"] is True, result["errors"]
    assert result["result"]["changed_fields"] == ["turn"]
    assert result["result"]["target_fields"] == ["turn"]
    assert stack["provider"].calls >= 1


def test_rewrite_tool_preserve_violation_is_rejected(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    payload = current_payload(stack, "ch_001")
    scripted(stack, {**payload, "turn": "新的转折", "title": "模型偷改的标题"})
    base = _base(stack)
    result = envelope(stack["dispatcher"], "rewrite_blueprint_node",
                      novel_id="novel_alpha", node_id="ch_001",
                      expected_revision=base, target_fields=["turn"],
                      instruction="改写转折")
    assert error_code(result) == "MCP_PRESERVE_VIOLATION"
    assert stack["repository"].current_revision("ch_001") == base


def test_approval_tools_preserve_semantics(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    base = _base(stack)
    accepted = envelope(stack["dispatcher"], "accept_revision",
                        novel_id="novel_alpha", node_id="ch_001",
                        expected_revision=base, reason="接受")
    assert accepted["ok"] is True
    assert accepted["result"]["decision"] == "accepted"
    assert accepted["result"]["reviewed_revision"] == base
    assert "quality pass ≠ accepted" in accepted["summary"]
    assert stack["repository"].get_current("ch_001").status == "accepted"
    # 已是 accepted → 幂等（不重复产生 revision）
    again = envelope(stack["dispatcher"], "accept_revision",
                     novel_id="novel_alpha", node_id="ch_001",
                     expected_revision=base, reason="再次确认")
    assert again["ok"] is True and again["revision"] == base
    assert again["result"]["idempotent"] is True
    rejected = envelope(stack["dispatcher"], "reject_revision",
                        novel_id="novel_alpha", node_id="ch_001",
                        revision=base,
                        reason="不采用")
    assert rejected["ok"] is True
    assert rejected["result"]["status"] == "recorded"
    assert stack["repository"].current_revision("ch_001") == base  # reject 不写 revision
    restored = envelope(stack["dispatcher"], "restore_revision",
                        novel_id="novel_alpha", node_id="ch_001",
                        from_revision=base - 1, expected_revision=base)
    assert restored["ok"] is True and restored["revision"] == base + 1
    assert stack["repository"].current_revision("ch_001") == base + 1
    assert stack["repository"].get_current("ch_001").status == "proposed"


def test_accept_revision_conflict_is_reported(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    base = _base(stack)
    envelope(stack["dispatcher"], "patch_blueprint_node", novel_id="novel_alpha",
             node_id="ch_001", expected_revision=base, changes={"hook": "x"})
    result = envelope(stack["dispatcher"], "accept_revision",
                      novel_id="novel_alpha", node_id="ch_001",
                      expected_revision=base)
    assert error_code(result) == "MCP_REVISION_CONFLICT"


def test_diff_tool_is_read_only(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    base = _base(stack)
    _patch(stack)
    result = envelope(stack["dispatcher"], "diff_revisions",
                      novel_id="novel_alpha", node_id="ch_001",
                      from_revision=base, to_revision=base + 1)
    assert result["ok"] is True
    assert result["result"]["changed_fields"] == ["hook"]
    assert result["read_only"] is True


def test_quality_tools(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path, clean=False, repairable=False)
    evaluated = envelope(stack["dispatcher"], "evaluate_blueprint",
                         novel_id="novel_alpha")
    assert evaluated["ok"] is False           # 有 blocker → ok=false
    assert evaluated["result"]["status"] in ("blocked", "failed")
    assert evaluated["issues"]
    plan = envelope(stack["dispatcher"], "plan_repair", novel_id="novel_alpha")
    assert plan["ok"] is True and plan["dry_run"] is True
    assert plan["result"]["steps"]
    assert plan["result"]["preview"]["preserve_fields"]
    assert stack["repository"].current_revision("sc_001_02") == 1
    verify = envelope(stack["dispatcher"], "verify_repair", novel_id="novel_alpha",
                      issue_ids=[plan["result"]["steps"][0]["issue_ids"][0]])
    assert verify["ok"] is False              # 未修复 → 未 resolved
    assert verify["result"]["status"] in ("partial", "unresolved", "regression")


def test_repair_tool_reports_needs_human_review(tmp_path: Path) -> None:
    """§24：needs_human_review 原样返回，不自动扩大 scope。"""

    stack = mcp_stack(tmp_path, clean=False, repairable=False)
    evaluated = envelope(stack["dispatcher"], "evaluate_blueprint",
                         novel_id="novel_alpha")
    issue_ids = [row["issue_id"] for row in evaluated["issues"]]
    result = envelope(stack["dispatcher"], "repair_issue", novel_id="novel_alpha",
                      issue_ids=issue_ids)
    assert result["ok"] is False
    assert error_code(result) in ("MCP_OPERATION_REQUIRES_REVIEW",
                                  "MCP_INVALID_ARGUMENT")


def test_delivery_tools(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    validated = envelope(stack["dispatcher"], "validate_delivery",
                         novel_id="novel_alpha", formats=["json"])
    assert validated["ok"] is True
    assert validated["read_only"] is True
    snapshot = envelope(stack["dispatcher"], "create_delivery_snapshot",
                        novel_id="novel_alpha", formats=["json", "markdown"])
    assert snapshot["ok"] is True
    snapshot_id = snapshot["result"]["snapshot_id"]
    delivered = envelope(stack["dispatcher"], "deliver_blueprint",
                         novel_id="novel_alpha", formats=["json", "markdown"])
    assert delivered["ok"] is True
    assert delivered["result"]["status"] == "delivered"
    assert len(delivered["result"]["artifacts"]) == 2
    assert delivered["result"]["llm_calls"] == 0        # §55：交付 0 LLM
    assert delivered["result"]["snapshot_id"] == snapshot_id


def test_delivery_tool_blocked_maps_to_stable_error(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path, clean=False)
    result = envelope(stack["dispatcher"], "deliver_blueprint",
                      novel_id="novel_alpha", formats=["json"])
    assert result["ok"] is False
    assert error_code(result) == "MCP_DELIVERY_BLOCKED"
    assert result["errors"][0]["cause"] == "DELIVERY_VALIDATION_FAILED"
    assert result["errors"][0]["details"]["novel_id"] == "novel_alpha"


def test_delivery_tool_defaults_to_accepted(tmp_path: Path) -> None:
    """§26：MCP 默认 selection 仍是 accepted，不因 Agent 方便而改成 current。"""

    stack = mcp_stack(tmp_path, clean=False)
    validated = envelope(stack["dispatcher"], "validate_delivery",
                         novel_id="novel_alpha", formats=["json"])
    snapshot = validated["result"]["snapshot"]
    assert snapshot["selection_mode"] == "accepted"
    assert not snapshot["node_revisions"]              # 没有 accepted → 空快照
    assert validated["ok"] is False


def test_delivery_artifact_resource_after_tool(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    delivered = envelope(stack["dispatcher"], "deliver_blueprint",
                         novel_id="novel_alpha", formats=["json"])
    snapshot_id = delivered["result"]["snapshot_id"]
    manifest = envelope_result = stack["dispatcher"].read_resource(
        f"novelforge://novels/novel_alpha/delivery/{snapshot_id}/manifest")
    assert manifest.mime_type == "application/json"
    assert "checksum" in manifest.content
    assert envelope_result is not None


def test_tool_invocations_are_observable_without_secrets(tmp_path: Path) -> None:
    stack = mcp_stack(tmp_path)
    _patch(stack)
    records = stack["dispatcher"].invocations()
    assert records[-1]["name"] == "patch_blueprint_node"
    assert records[-1]["novel_id"] == "novel_alpha"
    assert records[-1]["status"] == "ok"
    blob = json.dumps(records, ensure_ascii=False)
    assert "api_key" not in blob and "prompt" not in blob
    assert "F:\\" not in blob
