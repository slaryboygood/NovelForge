"""M5：统一 Planning analysis finding（M4 的 GraphFinding 抽象成通用结构）。

结构：code / severity / domain / source_id / related_ids / message / evidence / revision_id。
M4 的 `GraphFinding` 与 `GraphReport` 仍然可用（本模块是它们的通用父类型），
所以 M15 Repair Center 可以统一消费所有 planning findings。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from novelforge.models import StrictModel

Severity = Literal["ERROR", "WARNING", "INFO"]


class PlanningFinding(StrictModel):
    code: str = Field(min_length=3, max_length=64)
    severity: Severity = "ERROR"
    domain: str = Field(default="general", max_length=32)
    source_id: str = Field(default="", max_length=160)
    related_ids: list[str] = Field(default_factory=list)
    message: str = Field(default="", max_length=300)
    evidence: dict[str, object] = Field(default_factory=dict)


class AnalysisReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    content_digest: str = Field(default="", max_length=64)
    findings: list[PlanningFinding] = Field(default_factory=list)

    def errors(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity == "ERROR"]

    def warnings(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity == "WARNING"]

    def infos(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity == "INFO"]

    def ok(self) -> bool:
        return not self.errors()

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})

    def by_severity(self) -> dict[str, int]:
        rows = {"ERROR": 0, "WARNING": 0, "INFO": 0}
        for item in self.findings:
            rows[item.severity] = rows.get(item.severity, 0) + 1
        return rows

    def extend(self, findings: list[PlanningFinding]) -> None:
        self.findings.extend(findings)


def add_finding(findings: list[PlanningFinding], code: str, severity: Severity, domain: str,
                source_id: str, message: str, *, related: tuple[str, ...] = (),
                **evidence: object) -> None:
    findings.append(PlanningFinding(
        code=code, severity=severity, domain=domain, source_id=source_id,
        related_ids=sorted({item for item in related if item}), message=message[:300],
        evidence={key: value for key, value in evidence.items() if value is not None}))


__all__ = ["AnalysisReport", "PlanningFinding", "Severity", "add_finding"]
