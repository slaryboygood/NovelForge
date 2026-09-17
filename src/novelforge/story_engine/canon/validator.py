"""C06：SourceReferenceValidator —— 引用必须真的支持被声明的事实。

第一层永远是 deterministic：用结构化 identity 判断，不让 LLM 猜“像不像”。
只有 legacy 自然语言来源没有结构化事实 ID 时，才允许 inferred 判断并降低 confidence。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from novelforge.models import StrictModel

from .models import CanonSourceRef
from .repository import CanonRepository
from .service import CanonService


class SourceRefFinding(StrictModel):
    code: str
    source_ref: str = Field(default="", max_length=160)
    claimed_fact_ids: list[str] = Field(default_factory=list)
    detail: str = Field(default="", max_length=300)


class SourceRefReport(StrictModel):
    novel_id: str = Field(default="", max_length=96)
    findings: list[SourceRefFinding] = Field(default_factory=list)
    source_ref_missing_count: int = 0
    source_ref_semantic_mismatch_count: int = 0
    source_ref_future_leak_count: int = 0
    source_ref_status_mismatch_count: int = 0
    source_ref_scope_mismatch_count: int = 0
    promotion_conflict_count: int = 0

    def ok(self) -> bool:
        return not self.findings


class SourceReferenceValidator:
    def __init__(self, repository: CanonRepository) -> None:
        self.repository = repository
        self.service = CanonService(repository)

    # ---- source refs ------------------------------------------------------
    def validate_refs(self, novel_id: str, *, refs: list[CanonSourceRef],
                      claimed_fact_ids: list[str] | None = None,
                      temporal_cutoff: int | None = None,
                      character_scope: str = "") -> SourceRefReport:
        report = SourceRefReport(novel_id=novel_id)
        facts = {f.fact_id: f for f in self.repository.facts(novel_id)}
        for ref in refs:
            claimed = list(ref.claimed_fact_ids or claimed_fact_ids or [])
            label = ref.source_uuid or ref.chapter_uuid or ref.source_id or ref.source_type
            for fact_id in claimed:
                fact = facts.get(fact_id)
                if fact is None:
                    report.findings.append(SourceRefFinding(
                        code="SOURCE_REF_MISSING", source_ref=label,
                        claimed_fact_ids=[fact_id], detail="被引用的事实不存在"))
                    report.source_ref_missing_count += 1
                    continue
                allowed_sources = {item.source_id for item in fact.source_refs if item.source_id}
                allowed_sources |= {item.chapter_uuid for item in fact.source_refs if item.chapter_uuid}
                allowed_sources |= {item.chapter_uuid for item in fact.current_render_refs
                                    if item.chapter_uuid}
                if fact.first_occurrence_ref is not None:
                    allowed_sources.add(fact.first_occurrence_ref.chapter_uuid)
                if label and allowed_sources and label not in allowed_sources:
                    report.findings.append(SourceRefFinding(
                        code="SOURCE_REF_SEMANTIC_MISMATCH", source_ref=label,
                        claimed_fact_ids=[fact_id],
                        detail=f"{label} 不支持 {fact_id} 的声明"))
                    report.source_ref_semantic_mismatch_count += 1
                position = ref.temporal_position
                if position is None and fact.first_occurrence_ref is not None:
                    position = fact.first_occurrence_ref.display_number
                if temporal_cutoff is not None and position is not None and position > temporal_cutoff:
                    report.findings.append(SourceRefFinding(
                        code="SOURCE_REF_FUTURE_LEAK", source_ref=label,
                        claimed_fact_ids=[fact_id],
                        detail=f"引用位置 {position} 晚于 cutoff {temporal_cutoff}"))
                    report.source_ref_future_leak_count += 1
                if ref.provenance == "happened" and fact.status != "happened":
                    report.findings.append(SourceRefFinding(
                        code="SOURCE_REF_STATUS_MISMATCH", source_ref=label,
                        claimed_fact_ids=[fact_id],
                        detail=f"{fact_id} 当前状态是 {fact.status}，不能声称已发生"))
                    report.source_ref_status_mismatch_count += 1
            if character_scope:
                report.findings.extend(self._scope_findings(
                    novel_id, character_scope, claimed, label, report))
        return report

    def _scope_findings(self, novel_id: str, character_id: str, fact_ids: list[str],
                        label: str, report: SourceRefReport) -> list[SourceRefFinding]:
        known = {(entry.holder_id, entry.fact_id) for entry in self.repository.knowledge(novel_id)}
        findings: list[SourceRefFinding] = []
        for fact_id in fact_ids:
            if (character_id, fact_id) not in known:
                findings.append(SourceRefFinding(
                    code="SOURCE_REF_SCOPE_MISMATCH", source_ref=label,
                    claimed_fact_ids=[fact_id],
                    detail=f"{character_id} 无权知道 {fact_id}"))
                report.source_ref_scope_mismatch_count += 1
        return findings

    # ---- promotion --------------------------------------------------------
    def promotion_conflicts(self, novel_id: str) -> list[SourceRefFinding]:
        planned = [e for e in self.repository.events(novel_id) if e.status == "planned"]
        occurred = [e for e in self.repository.events(novel_id) if e.status == "occurred"]
        findings: list[SourceRefFinding] = []
        for event in planned:
            for candidate in occurred:
                if event.event_id == candidate.event_id:
                    continue
                if candidate.narrative_role != "canonical" and candidate.canonical_event_id:
                    # 已显式声明为 consequence / payoff / recurrence：不算冲突
                    continue
                if self._looks_same(event, candidate) == "conflict":
                    findings.append(SourceRefFinding(
                        code="PROMOTION_CONFLICT", source_ref=event.event_id,
                        claimed_fact_ids=[candidate.event_id],
                        detail="疑似同一事件但无法安全 promotion，需要显式处理"))
        return findings

    @staticmethod
    def _looks_same(planned: Any, occurred: Any) -> str:
        """返回 'same' / 'conflict' / 'different'。不确定时返回 conflict（不静默合并）。"""

        same_key = planned.canonical_key == occurred.canonical_key
        same_type = planned.event_type == occurred.event_type
        same_place = bool(planned.location) and planned.location == occurred.location
        shared = set(planned.subjects) & set(occurred.subjects)
        if same_key:
            return "same"
        # C11 加固：location / 参与者不完全一致但语义高度相似时，不能静默归为 different
        similar_name = _similarity(planned.canonical_name or planned.semantic_summary,
                                   occurred.canonical_name or occurred.semantic_summary) >= 0.5
        if same_type and shared and (same_place or similar_name):
            return "conflict" if not planned.can_repeat else "different"
        return "different"


def _tokens(text: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower())
    words = {word for word in clean.split() if len(word) > 1}
    grams = {clean[index:index + 2].strip() for index in range(max(0, len(clean) - 1))}
    return {token for token in words | grams if token}


def _similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0
