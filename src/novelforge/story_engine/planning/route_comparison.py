"""M7：Route 比较引擎 —— 20 个确定性维度 + tradeoff 报告（无伪造总分）。

结果全部是 derived analysis（`non_authoritative=True`）：verdict 只用
strong / acceptable / weak / blocked（pairwise 用 better / similar / worse），
不输出"Route A = 87.6"这类客观文学质量分；相对 signal 只用于候选间排序提示。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from novelforge.models import StrictModel

from .autonomous_actions import analyze_autonomous_actions
from .equipment_planning import analyze_equipment
from .findings import AnalysisReport, PlanningFinding
from .models import StoryPlanningIR
from .narrative_analysis import analyze_foreshadow, analyze_information, analyze_progression
from .plot_pressure import build_plot_pressure_inventory
from .requirements import validate_requirements
from .resource_planning import build_resource_ledger, validate_resources
from .rewards import analyze_reward_cadence
from .spine_analysis import analyze_story_spine, build_coverage_report, terminal_nodes
from .versioning import planning_digest

VERDICT_RANK: dict[str, int] = {"blocked": 0, "weak": 1, "acceptable": 2, "strong": 3}
Verdict = Literal["strong", "acceptable", "weak", "blocked"]
PairVerdict = Literal["better", "similar", "worse"]

DIMENSIONS: tuple[str, ...] = (
    "causal_coherence", "requirement_closure", "pressure_coverage", "character_arc_progress",
    "relationship_arc_progress", "faction_arc_progress", "conflict_escalation",
    "resource_feasibility", "equipment_feasibility", "location_feasibility",
    "information_pacing", "foreshadow_handling", "progression_quality", "reward_cadence",
    "autonomous_world_activity", "theme_linkage", "novelty", "repetition_risk",
    "dead_end_risk", "length_feasibility",
)


class RouteComparisonProfile(StrictModel):
    profile_id: str = Field(default="neutral", max_length=64)
    name: str = Field(default="neutral", max_length=64)
    dimension_weights: dict[str, float] = Field(default_factory=dict)
    note: str = Field(default="", max_length=300)
    non_authoritative: Literal[True] = True

    def weight(self, dimension: str) -> float:
        return float(self.dimension_weights.get(dimension, 1.0))


class DimensionResult(StrictModel):
    dimension: str = Field(min_length=3, max_length=48)
    verdict: Verdict = "acceptable"
    signals: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RouteDiff(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    base_digest: str = Field(default="", max_length=64)
    target_digest: str = Field(default="", max_length=64)
    nodes_added: list[str] = Field(default_factory=list)
    nodes_removed: list[str] = Field(default_factory=list)
    nodes_modified: list[str] = Field(default_factory=list)
    edges_added: list[str] = Field(default_factory=list)
    edges_removed: list[str] = Field(default_factory=list)
    pressure_delta: dict[str, int] = Field(default_factory=dict)
    coverage_delta: dict[str, int] = Field(default_factory=dict)
    requirement_delta: dict[str, int] = Field(default_factory=dict)
    conflict_delta: dict[str, int] = Field(default_factory=dict)
    resource_delta: dict[str, int] = Field(default_factory=dict)
    information_delta: dict[str, int] = Field(default_factory=dict)
    reward_delta: dict[str, int] = Field(default_factory=dict)
    story_notes: list[str] = Field(default_factory=list)
    non_authoritative: Literal[True] = True


class RouteCandidateAnalysis(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    status: str = Field(default="draft", max_length=16)
    content_digest: str = Field(default="", max_length=64)
    blocking_findings: list[PlanningFinding] = Field(default_factory=list)
    dimensions: list[DimensionResult] = Field(default_factory=list)
    diff: RouteDiff | None = None
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    unique_opportunities: list[str] = Field(default_factory=list)
    unresolved_pressures: list[str] = Field(default_factory=list)
    new_pressures: list[str] = Field(default_factory=list)
    requirement_closure: dict[str, int] = Field(default_factory=dict)
    coverage_delta: dict[str, int] = Field(default_factory=dict)
    structural_density: dict[str, Any] = Field(default_factory=dict)
    relative_signal: float = 0.0
    non_authoritative: Literal[True] = True

    def verdict(self, dimension: str) -> str:
        return next((item.verdict for item in self.dimensions
                     if item.dimension == dimension), "acceptable")


class RouteComparisonReport(StrictModel):
    session_id: str = Field(default="", max_length=64)
    source_revision: str = Field(default="", max_length=64)
    source_digest: str = Field(default="", max_length=64)
    profile_id: str = Field(default="neutral", max_length=64)
    candidates: list[RouteCandidateAnalysis] = Field(default_factory=list)
    recommended_candidate_id: str = Field(default="", max_length=64)
    recommendation_why: list[str] = Field(default_factory=list)
    tradeoff_summary: list[str] = Field(default_factory=list)
    non_authoritative: Literal[True] = True

    def analysis(self, candidate_id: str) -> RouteCandidateAnalysis | None:
        return next((item for item in self.candidates
                     if item.candidate_id == candidate_id), None)


class PairwiseComparison(StrictModel):
    left_id: str = Field(default="", max_length=64)
    right_id: str = Field(default="", max_length=64)
    better_by_dimension: dict[str, PairVerdict] = Field(default_factory=dict)
    tradeoffs: list[str] = Field(default_factory=list)
    non_authoritative: Literal[True] = True


class BaselineComparison(StrictModel):
    candidate_id: str = Field(default="", max_length=64)
    solved: list[str] = Field(default_factory=list)
    lost: list[str] = Field(default_factory=list)
    new_risks: list[str] = Field(default_factory=list)
    non_authoritative: Literal[True] = True


# ---------------------------------------------------------------- analysis
def analyze_candidate(plan: StoryPlanningIR, candidate_plan: StoryPlanningIR, *,
                      candidate_id: str, status: str = "draft",
                      profile: RouteComparisonProfile | None = None
                      ) -> RouteCandidateAnalysis:
    profile = profile or RouteComparisonProfile()
    reports: dict[str, AnalysisReport] = {
        "spine": analyze_story_spine(candidate_plan),
        "requirement": validate_requirements(candidate_plan),
        "resource": validate_resources(candidate_plan),
        "equipment": analyze_equipment(candidate_plan),
        "information": analyze_information(candidate_plan),
        "foreshadow": analyze_foreshadow(candidate_plan),
        "progression": analyze_progression(candidate_plan),
        "reward": analyze_reward_cadence(candidate_plan),
        "autonomous": analyze_autonomous_actions(candidate_plan),
    }
    inventory = build_plot_pressure_inventory(candidate_plan)
    coverage = build_coverage_report(candidate_plan, inventory=inventory)
    blocking = [item for report in reports.values()
                for item in report.findings if item.severity == "ERROR"]
    results = [
        _causal(reports["spine"], coverage),
        _requirement(coverage),
        _pressure(inventory, coverage),
        _ratio("character_arc_progress", coverage.character_arc_coverage,
               len(candidate_plan.character_arcs)),
        _ratio("relationship_arc_progress", coverage.relationship_arc_coverage,
               len(candidate_plan.relationship_arcs)),
        _ratio("faction_arc_progress", coverage.faction_arc_coverage,
               len(candidate_plan.faction_arcs)),
        _conflict(candidate_plan),
        _findings("resource_feasibility", reports["resource"],
                  extra={"deficits": len([row for row in build_resource_ledger(
                      candidate_plan).rows if row.impossible_consumption])}),
        _findings("equipment_feasibility", reports["equipment"]),
        _location(candidate_plan, reports["spine"]),
        _findings("information_pacing", reports["information"], warn_ok=4),
        _foreshadow(candidate_plan, reports["foreshadow"]),
        _findings("progression_quality", reports["progression"], warn_ok=3),
        _findings("reward_cadence", reports["reward"], warn_ok=3),
        _autonomous(candidate_plan, reports["autonomous"]),
        _theme(candidate_plan),
        _novelty(candidate_plan),
        _repetition(reports["spine"]),
        _dead_end(candidate_plan, coverage),
        _length(candidate_plan),
    ]
    relative = sum(profile.weight(item.dimension) * VERDICT_RANK.get(item.verdict, 2)
                   for item in results)
    analysis = RouteCandidateAnalysis(
        candidate_id=candidate_id, status=status,
        content_digest=planning_digest(candidate_plan), blocking_findings=blocking,
        dimensions=results, diff=route_diff(plan, candidate_plan, candidate_id=candidate_id),
        requirement_closure={"closed": coverage.requirement_closure,
                             "total": coverage.requirement_total},
        coverage_delta=_coverage_delta(build_coverage_report(plan), coverage),
        structural_density=_structural_density(candidate_plan),
        relative_signal=round(relative, 4))
    analysis.unresolved_pressures = [item.pressure_id for item in inventory.open()]
    analysis.new_pressures = sorted({item.pressure_id for item in inventory.pressures
                                     if item.state == "blocked"})
    analysis.unique_opportunities = sorted(
        {item.source_ref for item in inventory.pressures
         if item.kind in ("autonomous_action", "map_unlock", "reward_drought")
         and item.state == "open"})
    analysis.strengths = [f"{item.dimension}: {item.verdict}"
                          for item in results if item.verdict == "strong"]
    analysis.risks = ([f"{item.code}: {item.message}" for item in blocking]
                      + [f"{item.dimension}: {item.verdict}"
                         for item in results if item.verdict in ("weak", "blocked")])
    analysis.tradeoffs = [f"{' + '.join(item.notes)}" for item in results if item.notes]
    return analysis


def compare_candidates(plan: StoryPlanningIR, candidates: list[tuple[str, StoryPlanningIR]],
                       *, session_id: str = "", revision_id: str = "",
                       profile: RouteComparisonProfile | None = None
                       ) -> RouteComparisonReport:
    profile = profile or RouteComparisonProfile()
    analyses = [analyze_candidate(plan, candidate_plan, candidate_id=candidate_id,
                                  profile=profile)
                for candidate_id, candidate_plan in candidates]
    ready = [item for item in analyses if not item.blocking_findings]
    best = max(ready or analyses, key=lambda item: item.relative_signal)
    return RouteComparisonReport(
        session_id=session_id, source_revision=revision_id,
        source_digest=planning_digest(plan), profile_id=profile.profile_id,
        candidates=analyses, recommended_candidate_id=best.candidate_id if ready else "",
        recommendation_why=[("blocking ERROR 最少且 profile 权重下相对信号最高（只在候选之间比较，"
                            "不是客观质量分）") if ready else "所有候选都有 blocking ERROR，先修复再比较"],
        tradeoff_summary=[f"{item.candidate_id}: strengths={len(item.strengths)} "
                          f"risks={len(item.risks)} relative_signal={item.relative_signal}"
                          for item in analyses])


def compare_pairwise(plan: StoryPlanningIR, left_id: str, left_plan: StoryPlanningIR,
                     right_id: str, right_plan: StoryPlanningIR, *,
                     profile: RouteComparisonProfile | None = None
                     ) -> PairwiseComparison:
    left = analyze_candidate(plan, left_plan, candidate_id=left_id, profile=profile)
    right = analyze_candidate(plan, right_plan, candidate_id=right_id, profile=profile)
    better: dict[str, str] = {}
    tradeoffs: list[str] = []
    for dimension in DIMENSIONS:
        left_rank = VERDICT_RANK.get(left.verdict(dimension), 2)
        right_rank = VERDICT_RANK.get(right.verdict(dimension), 2)
        verdict = ("better" if left_rank > right_rank
                   else "worse" if left_rank < right_rank else "similar")
        better[dimension] = verdict
        if verdict != "similar":
            winner = left_id if verdict == "better" else right_id
            tradeoffs.append(f"{dimension}: {winner} 更好")
    return PairwiseComparison(left_id=left_id, right_id=right_id,
                              better_by_dimension=better, tradeoffs=tradeoffs)


def compare_with_baseline(plan: StoryPlanningIR, candidate_plan: StoryPlanningIR, *,
                          candidate_id: str,
                          profile: RouteComparisonProfile | None = None
                          ) -> BaselineComparison:
    base = analyze_candidate(plan, plan, candidate_id="baseline", profile=profile)
    target = analyze_candidate(plan, candidate_plan, candidate_id=candidate_id,
                               profile=profile)
    solved: list[str] = []
    lost: list[str] = []
    risks: list[str] = []
    for dimension in DIMENSIONS:
        base_rank = VERDICT_RANK.get(base.verdict(dimension), 2)
        target_rank = VERDICT_RANK.get(target.verdict(dimension), 2)
        if target_rank > base_rank:
            solved.append(dimension)
        elif target_rank < base_rank:
            lost.append(dimension)
        if target.verdict(dimension) in ("weak", "blocked") \
                and base.verdict(dimension) not in ("weak", "blocked"):
            risks.append(dimension)
    return BaselineComparison(candidate_id=candidate_id, solved=solved, lost=lost,
                              new_risks=sorted(set(risks)))


def route_diff(base_plan: StoryPlanningIR, target_plan: StoryPlanningIR, *,
               candidate_id: str = "") -> RouteDiff:
    """story-aware diff（不是 raw JSON diff）。"""

    base_nodes = {item.node_id: item for item in base_plan.plot_nodes}
    target_nodes = {item.node_id: item for item in target_plan.plot_nodes}
    added = sorted(set(target_nodes) - set(base_nodes))
    removed = sorted(set(base_nodes) - set(target_nodes))
    modified = sorted(node_id for node_id in set(base_nodes) & set(target_nodes)
                      if base_nodes[node_id].model_dump(mode="json")
                      != target_nodes[node_id].model_dump(mode="json"))
    base_edges = {(edge.from_node_id, edge.to_node_id, edge.relation)
                  for edge in (base_plan.spine.edges if base_plan.spine else [])}
    target_edges = {(edge.from_node_id, edge.to_node_id, edge.relation)
                    for edge in (target_plan.spine.edges if target_plan.spine else [])}
    base_inventory = build_plot_pressure_inventory(base_plan)
    target_inventory = build_plot_pressure_inventory(target_plan)
    base_coverage = build_coverage_report(base_plan, inventory=base_inventory)
    target_coverage = build_coverage_report(target_plan, inventory=target_inventory)
    base_information = sum(len(arc.moves) for arc in base_plan.information_arcs)
    target_information = sum(len(arc.moves) for arc in target_plan.information_arcs)
    base_rewards = len([event for plan_row in base_plan.reward_plans
                        for event in plan_row.events])
    target_rewards = len([event for plan_row in target_plan.reward_plans
                          for event in plan_row.events])
    return RouteDiff(
        candidate_id=candidate_id, base_digest=planning_digest(base_plan),
        target_digest=planning_digest(target_plan),
        nodes_added=added, nodes_removed=removed, nodes_modified=modified,
        edges_added=[f"{a}->{b}:{c}" for a, b, c in sorted(target_edges - base_edges)],
        edges_removed=[f"{a}->{b}:{c}" for a, b, c in sorted(base_edges - target_edges)],
        pressure_delta={"open": len(target_inventory.open()) - len(base_inventory.open()),
                        "blocked": len(target_inventory.blocked())
                        - len(base_inventory.blocked())},
        coverage_delta=_coverage_delta(base_coverage, target_coverage),
        requirement_delta={"closed": target_coverage.requirement_closure
                           - base_coverage.requirement_closure},
        conflict_delta={"chains": len(target_plan.conflict_chains)
                        - len(base_plan.conflict_chains)},
        resource_delta={"plans": len(target_plan.resource_plans) - len(base_plan.resource_plans),
                        "flows": len(target_plan.resource_flows) - len(base_plan.resource_flows)},
        information_delta={"moves": target_information - base_information},
        reward_delta={"events": target_rewards - base_rewards},
        story_notes=([f"+ {node_id}" for node_id in added[:5]]
                     + [f"- {node_id}" for node_id in removed[:5]]))


# ---------------------------------------------------------------- dimensions
def _causal(spine_report: AnalysisReport, coverage) -> DimensionResult:
    errors = [item for item in spine_report.findings if item.severity == "ERROR"]
    warnings = [item for item in spine_report.findings if item.severity == "WARNING"]
    verdict = ("blocked" if errors else "weak" if len(warnings) > 3
               else "strong" if not warnings else "acceptable")
    return DimensionResult(dimension="causal_coherence", verdict=verdict,
                           signals={"errors": len(errors), "warnings": len(warnings),
                                    "nodes": coverage.plot_node_count,
                                    "roots": coverage.root_count,
                                    "terminals": coverage.terminal_count})


def _requirement(coverage) -> DimensionResult:
    ratio = (coverage.requirement_closure / coverage.requirement_total
             if coverage.requirement_total else 1.0)
    verdict = ("strong" if ratio >= 0.9 else "acceptable" if ratio >= 0.6
               else "weak" if coverage.requirement_total else "acceptable")
    return DimensionResult(dimension="requirement_closure", verdict=verdict,
                           signals={"closed": coverage.requirement_closure,
                                    "total": coverage.requirement_total,
                                    "ratio": round(ratio, 4)})


def _pressure(inventory, coverage) -> DimensionResult:
    total = len(inventory.pressures)
    addressed = len(inventory.scheduled()) + len(inventory.resolved())
    ratio = (addressed / total) if total else 1.0
    verdict = ("strong" if ratio >= 0.6 else "acceptable" if ratio >= 0.35
               else "weak" if total else "acceptable")
    return DimensionResult(dimension="pressure_coverage", verdict=verdict,
                           signals={"addressed": addressed, "open": len(inventory.open()),
                                    "blocked": len(inventory.blocked()),
                                    "unaddressed": len(coverage.unaddressed_pressures)})


def _ratio(dimension: str, value: int, total: int) -> DimensionResult:
    ratio = (value / total) if total else 1.0
    verdict = ("strong" if ratio >= 0.8 else "acceptable" if ratio >= 0.5
               else "weak" if total else "acceptable")
    return DimensionResult(dimension=dimension, verdict=verdict,
                           signals={"covered": value, "total": total,
                                    "ratio": round(ratio, 4)})


def _conflict(plan) -> DimensionResult:
    stages = [stage for chain in plan.conflict_chains for stage in chain.stages]
    signals = sum(len(stage.escalation_signals()) for stage in stages)
    verdict = ("strong" if stages and signals >= len(stages) else
               "acceptable" if stages else "weak")
    return DimensionResult(dimension="conflict_escalation", verdict=verdict,
                           signals={"chains": len(plan.conflict_chains),
                                    "stages": len(stages), "escalation_signals": signals})


def _findings(dimension: str, report: AnalysisReport, *, warn_ok: int = 0,
              extra: dict[str, Any] | None = None) -> DimensionResult:
    errors = len([item for item in report.findings if item.severity == "ERROR"])
    warnings = len([item for item in report.findings if item.severity == "WARNING"])
    verdict = ("blocked" if errors else "weak" if warnings > warn_ok
               else "acceptable" if warnings else "strong")
    return DimensionResult(dimension=dimension, verdict=verdict,
                           signals={"errors": errors, "warnings": warnings,
                                    **(extra or {})})


def _location(plan, spine_report: AnalysisReport) -> DimensionResult:
    unreachable = len([item for item in spine_report.findings
                       if item.code == "LOCATION_UNREACHABLE_NODE"])
    blocked = len([item for item in spine_report.findings
                   if item.code == "LOCATION_BLOCKED_NODE"])
    verdict = ("blocked" if unreachable else "weak" if blocked > 2
               else "acceptable" if blocked else "strong")
    return DimensionResult(dimension="location_feasibility", verdict=verdict,
                           signals={"unreachable_nodes": unreachable,
                                    "blocked_nodes": blocked,
                                    "locations": len(plan.locations)})


def _foreshadow(plan, report: AnalysisReport) -> DimensionResult:
    debt = len([item for item in plan.foreshadow_plans
                if not any(move.move_type == "payoff" for move in item.moves)])
    result = _findings("foreshadow_handling", report, warn_ok=3,
                       extra={"unpaid_debt": debt})
    if plan.foreshadow_plans and debt > len(plan.foreshadow_plans) / 2:
        result.verdict = "weak"
    return result


def _autonomous(plan, report: AnalysisReport) -> DimensionResult:
    independent = len([item for item in plan.autonomous_actions
                       if not item.requires_protagonist_presence])
    verdict = ("strong" if independent >= 2 else "acceptable" if independent else "weak")
    if any(item.code == "AUTONOMOUS_ALWAYS_PROTAGONIST_DEPENDENT"
           for item in report.findings):
        verdict = "weak"
    return DimensionResult(dimension="autonomous_world_activity", verdict=verdict,
                           signals={"actions": len(plan.autonomous_actions),
                                    "protagonist_independent": independent})


def _theme(plan) -> DimensionResult:
    themed = len([node for node in plan.plot_nodes if node.theme_refs])
    verdict = "strong" if themed >= 2 else "acceptable" if themed else "weak"
    return DimensionResult(dimension="theme_linkage", verdict=verdict,
                           signals={"themed_nodes": themed,
                                    "has_theme": plan.theme is not None})


def _novelty(plan) -> DimensionResult:
    purposes = {node.purpose.strip() for node in plan.plot_nodes if node.purpose.strip()}
    locations = {node.location_id for node in plan.plot_nodes if node.location_id}
    participants = {tuple(sorted(node.participants)) for node in plan.plot_nodes
                    if node.participants}
    reward_types = {event.reward_type for plan_row in plan.reward_plans
                    for event in plan_row.events}
    nodes = max(1, len(plan.plot_nodes))
    diversity = round((len(purposes) / nodes + len(locations) / nodes
                       + len(participants) / nodes) / 3, 4)
    verdict = ("strong" if diversity >= 0.8 else "acceptable" if diversity >= 0.5
               else "weak")
    return DimensionResult(dimension="novelty", verdict=verdict,
                           signals={"purpose_diversity": round(len(purposes) / nodes, 4),
                                    "location_diversity": round(len(locations) / nodes, 4),
                                    "participant_diversity": round(len(participants) / nodes, 4),
                                    "reward_type_diversity": len(reward_types),
                                    "structural_only": True})


def _repetition(report: AnalysisReport) -> DimensionResult:
    hotspots = [item.source_id for item in report.findings
                if item.code == "PLOT_NODE_PATTERN_REPETITION"]
    verdict = ("blocked" if len(hotspots) > 3 else "weak" if hotspots else "strong")
    return DimensionResult(dimension="repetition_risk", verdict=verdict,
                           signals={"hotspots": hotspots[:10],
                                    "hotspot_count": len(hotspots)})


def _dead_end(plan, coverage) -> DimensionResult:
    terminals = terminal_nodes(plan)
    themed_terminal = [node.node_id for node in plan.plot_nodes
                       if node.node_id in terminals and node.theme_refs]
    open_pressures = coverage.open_pressure_count + coverage.blocked_pressure_count
    risks: list[str] = []
    if not terminals:
        risks.append("no_terminal")
    if plan.theme is not None and plan.theme.final_answer_direction \
            and not themed_terminal:
        risks.append("ending_direction_unplanned")
    if open_pressures == 0 and plan.plot_nodes and plan.theme is not None:
        risks.append("no_open_pressure_before_ending")
    verdict = "blocked" if "no_terminal" in risks else "weak" if risks else "strong"
    return DimensionResult(dimension="dead_end_risk", verdict=verdict,
                           signals={"terminals": terminals, "risks": risks,
                                    "open_pressures": open_pressures})


def _length(plan) -> DimensionResult:
    density = _structural_density(plan)
    verdict = {"too_small": "weak", "too_dense": "weak",
               "plausible": "acceptable", "unknown": "acceptable"}.get(
        str(density.get("verdict")), "acceptable")
    return DimensionResult(dimension="length_feasibility", verdict=verdict,
                           signals=density)


def _structural_density(plan) -> dict[str, Any]:
    """chapter-independent structural estimate（绝不输出章数）。"""

    nodes = len(plan.plot_nodes)
    must = len([node for node in plan.plot_nodes if node.must_happen])
    optional = len([node for node in plan.plot_nodes if node.optional])
    stages = sum(len(chain.stages) for chain in plan.conflict_chains)
    scheduled = len([node for node in plan.plot_nodes if node.scheduled_volume_id])
    if nodes == 0:
        verdict = "unknown"
    elif nodes < 4 and not stages:
        verdict = "too_small"
    elif stages + must > 3 * nodes:
        verdict = "too_dense"
    else:
        verdict = "plausible"
    return {"node_count": nodes, "must_happen": must, "optional": optional,
            "conflict_stages": stages, "scheduled_nodes": scheduled,
            "verdict": verdict, "chapter_independent": True}


def _coverage_delta(base, target) -> dict[str, int]:
    return {"nodes": target.plot_node_count - base.plot_node_count,
            "must_happen": target.must_happen_count - base.must_happen_count,
            "open_pressure": target.open_pressure_count - base.open_pressure_count,
            "blocked_pressure": target.blocked_pressure_count - base.blocked_pressure_count,
            "requirement_closed": target.requirement_closure - base.requirement_closure,
            "character_arc": target.character_arc_coverage - base.character_arc_coverage,
            "relationship_arc": (target.relationship_arc_coverage
                                 - base.relationship_arc_coverage),
            "faction_arc": target.faction_arc_coverage - base.faction_arc_coverage,
            "information": target.information_coverage - base.information_coverage,
            "foreshadow": target.foreshadow_coverage - base.foreshadow_coverage,
            "progression": target.progression_coverage - base.progression_coverage,
            "reward": target.reward_coverage - base.reward_coverage}


__all__ = [
    "DIMENSIONS",
    "VERDICT_RANK",
    "BaselineComparison",
    "DimensionResult",
    "PairwiseComparison",
    "RouteCandidateAnalysis",
    "RouteComparisonProfile",
    "RouteComparisonReport",
    "RouteDiff",
    "analyze_candidate",
    "compare_candidates",
    "compare_pairwise",
    "compare_with_baseline",
    "route_diff",
]
