"""Quality / Repair 工具（V4-08 §22–§24、§35–§36）：
MCP → application.services.review（不直接调用 evaluator / RepairExecutor）。
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from pydantic import Field

from ..contracts import ToolResult
from ..errors import MCPQualityBlocked, MCPRequiresReview
from ..uri import node_uri, quality_uri
from . import MCPInput, build_tool

QUALITY_ERRORS: tuple[str, ...] = (
    "MCP_INVALID_ARGUMENT", "MCP_NODE_NOT_FOUND", "MCP_OWNERSHIP_MISMATCH",
    "MCP_QUALITY_BLOCKED", "MCP_OPERATION_REQUIRES_REVIEW", "MCP_LLM_UNAVAILABLE",
)


class EvaluateInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(default="", max_length=64)
    gates: list[str] = Field(default_factory=list, max_length=12)


class PlanRepairInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    node_id: str = Field(default="", max_length=64)
    issue_ids: list[str] = Field(default_factory=list, max_length=64)
    dry_run: bool = True


class RepairInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    issue_ids: list[str] = Field(min_length=1, max_length=64)
    dry_run: bool = False
    idempotency_key: str = Field(default="", max_length=128)


class VerifyInput(MCPInput):
    novel_id: str = Field(min_length=1, max_length=96)
    issue_ids: list[str] = Field(default_factory=list, max_length=64)


def _evaluate(context: Any, payload: EvaluateInput) -> ToolResult:
    if payload.node_id:
        report = context.editor.evaluate(payload.node_id,
                                        gates=tuple(payload.gates) or None)
    else:
        report = context.review.evaluate(gates=tuple(payload.gates) or None)
        report = report.as_dict() if hasattr(report, "as_dict") else dict(report)
    status = str(report.get("status") or "")
    issues = tuple(report.get("issues") or ())
    return ToolResult(
        operation="evaluate_blueprint", novel_id=payload.novel_id,
        ok=status == "passed", revision=0, result=dict(report), issues=issues,
        resources=(quality_uri(payload.novel_id),
                   node_uri(payload.novel_id, payload.node_id))
        if payload.node_id else (quality_uri(payload.novel_id),),
        summary=f"quality status={status}，issues={len(issues)}")


def _plan_repair(context: Any, payload: PlanRepairInput) -> ToolResult:
    plan = context.editor.plan_repair(node_id=payload.node_id,
                                      issue_ids=tuple(payload.issue_ids),
                                      dry_run=True)
    plan = plan.as_dict() if hasattr(plan, "as_dict") else dict(plan or {})
    return ToolResult(
        operation="plan_repair", novel_id=payload.novel_id, ok=True,
        dry_run=True, result=plan,
        resources=(quality_uri(payload.novel_id),),
        summary=(f"repair plan status={plan.get('status')}，"
                 f"steps={len(plan.get('steps') or [])}"))


def _repair(context: Any, payload: RepairInput) -> ToolResult:
    outcome = context.review.repair_issue(list(payload.issue_ids),
                                          dry_run=payload.dry_run,
                                          idempotency_key=payload.idempotency_key)
    payload_dict = outcome.as_dict() if hasattr(outcome, "as_dict") else dict(outcome)
    verification = dict(payload_dict.get("verification") or {})
    status = str(verification.get("status") or payload_dict.get("status") or "")
    revisions = (payload_dict.get("result") or {}).get("after_revisions") or {}
    result_revision = max([int(value) for value in revisions.values()] or [0])
    if status in ("partial", "unresolved"):
        raise MCPRequiresReview(f"repair 未完全解决：{status}",
                                details={"issue_ids": list(payload.issue_ids),
                                         "verification_status": status})
    return ToolResult(
        operation="repair_issue", novel_id=payload.novel_id, ok=True,
        revision=result_revision, result=payload_dict,
        resources=(quality_uri(payload.novel_id),),
        summary=f"repair {list(payload.issue_ids)} → {status or 'applied'}")


def _verify(context: Any, payload: VerifyInput) -> ToolResult:
    verification = context.editor.verify_repair(issue_ids=tuple(payload.issue_ids))
    data = verification.as_dict() if hasattr(verification, "as_dict") \
        else dict(verification)
    return ToolResult(
        operation="verify_repair", novel_id=payload.novel_id,
        ok=str(data.get("status")) == "resolved", result=data,
        resources=(quality_uri(payload.novel_id),),
        summary=(f"verify status={data.get('status')}，"
                 f"resolved={len(data.get('resolved_issue_ids') or [])}"))


def register(registry: Any) -> None:
    rows = (
        dict(name="evaluate_blueprint", description="运行 Quality Gate（Q0–Q9）",
             dto=EvaluateInput, impl=_evaluate, read_only=False, expensive=True,
             service="application.services.review.evaluate"),
        dict(name="plan_repair", description="生成 repair plan（dry-run，不写 revision）",
             dto=PlanRepairInput, impl=_plan_repair, read_only=True,
             supports_dry_run=True, service="application.services.review.plan_repair"),
        dict(name="repair_issue", description="执行定向修复（可能产生新 revision）",
             dto=RepairInput, impl=_repair, expensive=True, supports_dry_run=True,
             service="application.services.review.repair_issue"),
        dict(name="verify_repair", description="复核修复结果（只读）",
             dto=VerifyInput, impl=_verify, read_only=True,
             service="application.services.review.verify_repair"),
    )
    for row in rows:
        spec, handler = build_tool(output_schema={"type": "object"},
                                   possible_errors=QUALITY_ERRORS, idempotent=True,
                                   **row)
        registry.register(spec, handler)


__all__ = ["EvaluateInput", "PlanRepairInput", "QUALITY_ERRORS", "RepairInput",
           "VerifyInput", "register"]
