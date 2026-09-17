"""M5：Structured Requirement System。

- `RequirementRef` / `RequirementGroup(all|any)` 是 Planning 对**未来设计要求**的表达；
- Planning requirement 不能宣布"已经满足"：`evaluate_requirements` 只接受**外部 supplied
  context**（M7 Route Lab 以后提供 hypothetical context），不写 StoryState / Canon；
- 旧自由文本（`entry_requirement` / `requirement`）继续保留给作者展示，可被
  `legacy_requirement_group()` 转成结构化引用，并在 validator 中作为 legacy fallback。
"""

from __future__ import annotations

import re
from typing import Iterable, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .findings import AnalysisReport, PlanningFinding, add_finding
from .models import (
    RequirementGroup,
    RequirementRef,
    StoryPlanningIR,
    new_planning_id,
)

LEGACY_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]*_[A-Z0-9_]+)\b")
TOKEN_KIND: dict[str, str] = {
    "RULE": "world_rule", "FACT": "fact", "KNW": "knowledge", "ABILITY": "ability",
    "TRACK": "progression", "TRACKMILE": "progression", "RPLAN": "resource",
    "RFLOW": "resource", "EQ": "equipment", "RELARC": "relationship",
    "FACTION": "faction", "LOC": "location", "NODE": "plot_node",
}


class RequirementEvaluation(StrictModel):
    requirement_id: str = Field(default="", max_length=64)
    satisfied: bool = False
    reason: str = Field(default="", max_length=200)


class RequirementEvaluationReport(StrictModel):
    """只用**外部 supplied context** 评估，不改变任何 Planning / StoryState。"""

    operator: Literal["all", "any"] = "all"
    context_source: str = Field(default="supplied", max_length=64)
    rows: list[RequirementEvaluation] = Field(default_factory=list)
    satisfied: bool = False

    def missing(self) -> list[str]:
        return [row.requirement_id for row in self.rows if not row.satisfied]


def evaluate_requirements(group: RequirementGroup | None, *,
                          available: Iterable[str] = (),
                          reason_map: dict[str, str] | None = None,
                          context_source: str = "supplied") -> RequirementEvaluationReport:
    """all：全部满足；any：任一满足。未出现在 available 里的要求一律视为未满足。"""

    if group is None:
        return RequirementEvaluationReport(satisfied=True, context_source=context_source)
    known = set(available)
    reasons = reason_map or {}
    rows = [RequirementEvaluation(
        requirement_id=ref.requirement_id,
        satisfied=(ref.requirement_id in known
                   or bool(set(ref.satisfied_by) & known)
                   or (bool(ref.ref_id) and ref.ref_id in known)),
        reason=reasons.get(ref.requirement_id, "context 未提供" if ref.requirement_id not in known
                           else "context 已满足"))
        for ref in group.requirements]
    satisfied = all(row.satisfied for row in rows) if group.operator == "all" \
        else any(row.satisfied for row in rows)
    return RequirementEvaluationReport(operator=group.operator, rows=rows,
                                       satisfied=satisfied, context_source=context_source)


def legacy_requirement_group(text: str, *, kind: str = "custom",
                             description: str = "") -> RequirementGroup | None:
    """把自由文本（如 "RULE_OATH" / "需要镇务会放行"）转成结构化引用（legacy fallback）。"""

    if not (text or "").strip():
        return None
    tokens = LEGACY_TOKEN.findall(text)
    if not tokens:
        return RequirementGroup(operator="all", requirements=[RequirementRef(
            requirement_id=new_planning_id("requirement"), kind=kind,  # type: ignore[arg-type]
            description=description or text.strip(), provenance="inferred")],
            description=text.strip())
    refs = [RequirementRef(requirement_id=new_planning_id("requirement"),
                           kind=TOKEN_KIND.get(token.split("_", 1)[0], kind),  # type: ignore[arg-type]
                           ref_id=token, description=text.strip(), provenance="inferred")
            for token in tokens]
    return RequirementGroup(operator="all", requirements=refs, description=text.strip())


def stage_trigger_node(stage) -> str:
    """显式 trigger_node_id 优先；否则回退到 trigger 文本里的 NODE_ token（legacy）。"""

    explicit = getattr(stage, "trigger_node_id", "")
    if explicit:
        return explicit
    for token in LEGACY_TOKEN.findall(getattr(stage, "trigger", "") or ""):
        if token.startswith("NODE_"):
            return token
    return ""


def requirement_targets(plan: StoryPlanningIR) -> dict[str, str]:
    """所有可作为 requirement 目标的稳定 ID → kind（不含 planning-only）。"""

    rows: dict[str, str] = {}
    for item in (plan.world.world_rules if plan.world else []):
        rows[item.rule_id] = "world_rule"
    for item in plan.characters:
        rows[item.character_id] = "relationship"
    for item in plan.relationship_arcs:
        rows[item.arc_id] = "relationship"
    for item in plan.factions:
        rows[item.faction_id] = "faction"
    for item in plan.locations:
        rows[item.location_id] = "location"
    for item in plan.plot_nodes:
        rows[item.node_id] = "plot_node"
    for arc in plan.information_arcs:
        for truth in arc.truths:
            rows[truth.truth_id] = "knowledge"
    for item in plan.unit_defs:
        rows[item.unit_id] = "custom"
    for item in plan.resource_plans:
        rows[item.identity()] = "resource"
    for item in plan.equipment_plans:
        rows[item.equipment_id] = "equipment"
    for item in plan.progression_tracks:
        rows[item.track_id] = "progression"
        for milestone in item.milestones:
            rows[milestone.milestone_id] = "progression"
    return rows


def validate_requirements(plan: StoryPlanningIR, *, revision_id: str = "") -> AnalysisReport:
    """校验所有内联 RequirementGroup：ref 存在、kind 匹配、空 requirement。"""

    report = AnalysisReport(novel_id=plan.novel_id, planning_id=plan.planning_id,
                            revision_id=revision_id)
    targets = requirement_targets(plan)
    findings: list[PlanningFinding] = []
    for group in plan.requirement_groups():
        for ref in group.requirements:
            if not ref.ref_id and not ref.condition and not ref.description:
                add_finding(findings, "REQUIREMENT_EMPTY", "WARNING", "requirement",
                            ref.requirement_id, "requirement 没有任何 ref_id / 条件 / 说明")
                continue
            if not ref.ref_id:
                continue
            if ref.ref_id not in targets:
                add_finding(findings, "REQUIREMENT_UNKNOWN_REF", "ERROR", "requirement",
                            ref.requirement_id, "requirement 指向不存在的 planning 对象",
                            related=(ref.ref_id,), kind=ref.kind)
                continue
            actual = targets[ref.ref_id]
            if ref.kind not in ("custom", actual):
                add_finding(findings, "REQUIREMENT_KIND_MISMATCH", "WARNING", "requirement",
                            ref.requirement_id, "requirement kind 与实际对象类型不一致",
                            related=(ref.ref_id,), declared=ref.kind, actual=actual)
    report.findings.extend(findings)
    return report


__all__ = [
    "LEGACY_TOKEN",
    "RequirementEvaluation",
    "RequirementEvaluationReport",
    "evaluate_requirements",
    "legacy_requirement_group",
    "requirement_targets",
    "stage_trigger_node",
    "validate_requirements",
]
