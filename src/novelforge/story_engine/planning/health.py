"""M5：PlanningHealthReport —— 长线规划健康度汇总（三态，不给假精确总分）。

汇总 domain：progression / resource / equipment / base / map / information / foreshadow /
reward / autonomous / faction_relation / graph（M4）。
每个 domain 只给 ERROR / WARNING / INFO 计数与三态：

- `healthy`：没有 ERROR / WARNING；
- `needs_attention`：有 WARNING 但没有 ERROR；
- `blocked`：存在 ERROR。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

from .autonomous_actions import analyze_autonomous_actions, analyze_faction_relations
from .base_map import analyze_base_progression, analyze_map_expansion
from .equipment_planning import analyze_equipment
from .findings import AnalysisReport, PlanningFinding
from .graph_validator import PlanningGraphValidator
from .models import StoryPlanningIR
from .narrative_analysis import analyze_foreshadow, analyze_information, analyze_progression
from .resource_planning import validate_resources
from .rewards import analyze_reward_cadence
from .requirements import validate_requirements
from .versioning import planning_digest

HealthState = Literal["healthy", "needs_attention", "blocked"]

DOMAIN_ANALYZERS = {
    "progression": analyze_progression,
    "resource": validate_resources,
    "equipment": analyze_equipment,
    "base": analyze_base_progression,
    "map": analyze_map_expansion,
    "information": analyze_information,
    "foreshadow": analyze_foreshadow,
    "reward": analyze_reward_cadence,
    "autonomous": analyze_autonomous_actions,
    "faction_relation": analyze_faction_relations,
    "requirement": validate_requirements,
}


class DomainHealth(StrictModel):
    domain: str = Field(min_length=2, max_length=32)
    state: HealthState = "healthy"
    error: int = 0
    warning: int = 0
    info: int = 0
    codes: list[str] = Field(default_factory=list)


class PlanningHealthReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    overall_state: HealthState = "healthy"
    domains: list[DomainHealth] = Field(default_factory=list)
    findings: list[PlanningFinding] = Field(default_factory=list)
    read_only: Literal[True] = True

    def domain(self, name: str) -> DomainHealth | None:
        return next((item for item in self.domains if item.domain == name), None)

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})


def analyze_planning_health(plan: StoryPlanningIR, *, revision_id: str = "",
                            known_entity_ids: tuple[str, ...] = (),
                            include_graph: bool = True) -> PlanningHealthReport:
    """跑全部 long-form analyzer + （可选）M4 graph validator，汇总三态健康度。"""

    findings: list[PlanningFinding] = []
    domains: list[DomainHealth] = []
    reports: dict[str, AnalysisReport] = {}
    for domain, analyzer in DOMAIN_ANALYZERS.items():
        report = analyzer(plan, revision_id=revision_id)
        reports[domain] = report
        findings.extend(report.findings)
        domains.append(_domain_health(domain, report.findings))
    if include_graph:
        graph_report = PlanningGraphValidator(known_entity_ids=known_entity_ids).validate(
            plan, revision_id=revision_id)
        findings.extend(graph_report.findings)
        domains.append(_domain_health("graph", graph_report.findings))
    states = [item.state for item in domains]
    overall: HealthState = "blocked" if "blocked" in states else (
        "needs_attention" if "needs_attention" in states else "healthy")
    return PlanningHealthReport(
        novel_id=plan.novel_id, planning_id=plan.planning_id, revision_id=revision_id,
        content_digest=planning_digest(plan), overall_state=overall,
        domains=sorted(domains, key=lambda item: item.domain),
        findings=findings)


def _domain_health(domain: str, findings: list[PlanningFinding]) -> DomainHealth:
    errors = [item for item in findings if item.severity == "ERROR"]
    warnings = [item for item in findings if item.severity == "WARNING"]
    infos = [item for item in findings if item.severity == "INFO"]
    state: HealthState = "blocked" if errors else ("needs_attention" if warnings
                                                   else "healthy")
    return DomainHealth(domain=domain, state=state, error=len(errors),
                        warning=len(warnings), info=len(infos),
                        codes=sorted({item.code for item in findings}))


__all__ = [
    "DOMAIN_ANALYZERS",
    "DomainHealth",
    "HealthState",
    "PlanningHealthReport",
    "analyze_planning_health",
]
