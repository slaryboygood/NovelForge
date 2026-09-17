"""M2B：PlanningValidationService —— 在模型 validator 之上加 revision / lineage 检查。

检查项（M2B §15）：

- stable ref existence / duplicate IDs / broken graph refs（来自 PlanningValidator）；
- StorySpine DAG、PlotNode dependency、Volume / Arc / CharacterArc / Relationship /
  Faction / LocationGraph / Timeline / Information / Foreshadow / Progression refs；
- version lineage（parent 存在、revision 递增、planning_id 一致、branch head 可解析）；
- planning detail level compatibility（来自 PlanningValidator）；
- scheduled PlotNode execution uniqueness（来自 PlanningValidator）；
- content digest 与落盘内容一致（防篡改 / 防手改）。
"""

from __future__ import annotations

from typing import Iterable

from pydantic import Field

from novelforge.models import StrictModel

from .models import StoryPlanningIR
from .repository import (
    PlanningRepository,
    PlanningRepositoryError,
    PlanningRevisionRecord,
)
from .schemas import PlanningGateError, validate_planning_ir
from .validator import PlanningFinding, PlanningReport, PlanningValidator
from .versioning import planning_digest


class PlanningValidationError(RuntimeError):
    def __init__(self, report: "PlanningValidationReport") -> None:
        self.report = report
        super().__init__("PLANNING_VALIDATION_FAILED: "
                         + "; ".join(item.code for item in report.errors()[:5]))


class PlanningValidationReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    planning_id: str = Field(default="", max_length=64)
    revision_id: str = Field(default="", max_length=64)
    digest_ok: bool = False
    findings: list[PlanningFinding] = Field(default_factory=list)

    def errors(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity == "error"]

    def warnings(self) -> list[PlanningFinding]:
        return [item for item in self.findings if item.severity != "error"]

    def ok(self) -> bool:
        return not self.errors()

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings})


class PlanningValidationService:
    def __init__(self, repository: PlanningRepository | None = None, *,
                 known_entity_ids: Iterable[str] = (), known_canon_ids: Iterable[str] = (),
                 known_chapter_ir_ids: Iterable[str] = (),
                 allow_external_refs: bool = True) -> None:
        self.repository = repository
        self.validator = PlanningValidator(known_entity_ids=known_entity_ids,
                                           known_canon_ids=known_canon_ids,
                                           known_chapter_ir_ids=known_chapter_ir_ids,
                                           allow_external_refs=allow_external_refs)

    # ---------------------------------------------------------------- plan
    def validate_plan(self, plan: StoryPlanningIR, *,
                      previous: StoryPlanningIR | None = None) -> PlanningValidationReport:
        report = PlanningValidationReport(novel_id=plan.novel_id,
                                          planning_id=plan.planning_id,
                                          digest_ok=True)
        try:
            validate_planning_ir(plan.model_dump(mode="json"))
        except PlanningGateError as error:
            report.digest_ok = False
            for issue in error.issues:
                report.findings.append(PlanningFinding(
                    code=error.code, path="plan", message="strict schema 校验失败",
                    detail=issue[:400]))
            return report
        inner: PlanningReport = self.validator.validate(plan, previous=previous)
        report.findings.extend(inner.findings)
        report.digest_ok = True
        return report

    # ---------------------------------------------------------------- revision
    def validate_revision(self, revision_id: str, *,
                          previous_revision_id: str = "") -> PlanningValidationReport:
        if self.repository is None:
            raise PlanningValidationError(PlanningValidationReport(
                revision_id=revision_id,
                findings=[PlanningFinding(code="REPOSITORY_REQUIRED", path="repository",
                                          message="validate_revision 需要 repository")]))
        try:
            record = self.repository.load(revision_id)
        except PlanningRepositoryError as error:
            return PlanningValidationReport(
                revision_id=revision_id, digest_ok=False,
                findings=[PlanningFinding(code=error.code, path="revision",
                                          message=error.message)])
        report = PlanningValidationReport(novel_id=record.novel_id,
                                          planning_id=record.planning_id,
                                          revision_id=revision_id, digest_ok=False)
        digest = planning_digest(record.plan)
        report.digest_ok = digest == record.content_digest
        if not report.digest_ok:
            report.findings.append(PlanningFinding(
                code="PLANNING_CONTENT_DIGEST_MISMATCH", path="content_digest",
                message="落盘内容与 revision 摘要不一致",
                detail=f"{record.content_digest} != {digest}"))
        report.findings.extend(self.validate_plan(record.plan).findings)
        report.findings.extend(self._lineage_findings(record, previous_revision_id))
        return report

    def assert_revision_ok(self, revision_id: str, *,
                           previous_revision_id: str = "") -> PlanningValidationReport:
        report = self.validate_revision(revision_id, previous_revision_id=previous_revision_id)
        if not report.ok():
            raise PlanningValidationError(report)
        return report

    # ---------------------------------------------------------------- lineage
    def _lineage_findings(self, record: PlanningRevisionRecord,
                          previous_revision_id: str) -> list[PlanningFinding]:
        findings: list[PlanningFinding] = []
        repository = self.repository
        assert repository is not None
        parent_id = record.parent_revision_id
        if parent_id:
            if not repository.exists(parent_id):
                findings.append(PlanningFinding(code="REVISION_PARENT_MISSING", path="parent",
                                                message="parent revision 不存在", detail=parent_id))
            else:
                parent = repository.load(parent_id)
                if parent.revision >= record.revision:
                    findings.append(PlanningFinding(
                        code="REVISION_LINEAGE_BROKEN", path="revision",
                        message="revision 序号必须大于 parent",
                        detail=f"{parent.revision} >= {record.revision}"))
                if parent.planning_id != record.planning_id:
                    findings.append(PlanningFinding(
                        code="PLANNING_ID_MISMATCH", path="planning_id",
                        message="同一 lineage 的 planning_id 必须一致",
                        detail=f"{parent.planning_id} != {record.planning_id}"))
        head_id = repository.list_branches().get(record.branch_id, "")
        if not head_id:
            findings.append(PlanningFinding(code="BRANCH_HEAD_UNKNOWN", path="branch_id",
                                            message="分支没有 head",
                                            detail=record.branch_id))
        else:
            lineage = {row.revision_id for row in repository.lineage(head_id)}
            if record.revision_id not in lineage:
                findings.append(PlanningFinding(
                    code="REVISION_NOT_IN_BRANCH_LINEAGE", path="branch_id",
                    message="revision 不在该分支 lineage 上", detail=record.branch_id))
        if previous_revision_id:
            previous = repository.load(previous_revision_id)
            if previous.planning_id != record.planning_id:
                findings.append(PlanningFinding(
                    code="PLANNING_ID_MISMATCH", path="planning_id",
                    message="对比的两个 revision 属于不同 planning",
                    detail=f"{previous.planning_id} != {record.planning_id}"))
        return findings


__all__ = [
    "PlanningValidationError",
    "PlanningValidationReport",
    "PlanningValidationService",
]
