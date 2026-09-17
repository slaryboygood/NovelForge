"""S02：Chapter IR Validator —— 结构 + evidence + typed state + writer-visible 四层合并校验。"""

from __future__ import annotations

from pydantic import Field

from novelforge.models import StrictModel
from novelforge.story_engine.canon.context import contains_writer_metadata

from .evidence import EvidenceFinding, EvidenceValidator
from .models import ChapterSemanticIR
from .state import StateFinding, TypedStateRegistry


class IRReport(StrictModel):
    chapter_uuid: str = ""
    findings: list[EvidenceFinding] = Field(default_factory=list)
    state_findings: list[StateFinding] = Field(default_factory=list)

    def ok(self) -> bool:
        return not [item for item in self.findings if item.severity == "error"] \
            and not self.state_findings

    def codes(self) -> list[str]:
        return sorted({item.code for item in self.findings} |
                      {item.code for item in self.state_findings})


class ChapterIRValidator:
    def __init__(self, *, registry: TypedStateRegistry | None = None,
                 evidence: EvidenceValidator | None = None) -> None:
        self.registry = registry
        self.evidence = evidence or EvidenceValidator()

    def validate(self, ir: ChapterSemanticIR, *,
                 candidate_fields: dict[str, str] | None = None) -> IRReport:
        report = IRReport(chapter_uuid=ir.chapter_uuid)
        report.findings.extend(self.evidence.validate(
            ir, candidate_fields=candidate_fields).findings)
        if self.registry is not None:
            report.state_findings.extend(
                self.registry.validate(ir.state_transitions,
                                       chapter_position=ir.temporal_position))
        # Writer-visible 文本不得含 machine-only 元数据（复用 canon prose 的判定）
        for field_name, text in (candidate_fields or {}).items():
            if text and contains_writer_metadata(text):
                report.findings.append(EvidenceFinding(
                    code="WRITER_VISIBLE_METADATA_LEAK", field_name=field_name,
                    detail="writer-visible 文本含内部 ID / 章节号"))
        return report

    def validate_many(self, chapters: list[ChapterSemanticIR], *,
                      candidate_fields: dict[str, dict[str, str]] | None = None
                      ) -> dict[str, IRReport]:
        return {ir.chapter_uuid: self.validate(
            ir, candidate_fields=(candidate_fields or {}).get(ir.chapter_uuid))
            for ir in chapters}
