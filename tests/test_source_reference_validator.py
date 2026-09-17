"""C06：SourceReferenceValidator（错误引用 / 未来泄漏 / 状态与范围 / promotion conflict）。"""

from __future__ import annotations

from novelforge.story_engine.canon.models import (
    CanonEvent,
    CanonFact,
    CanonKnowledge,
    CanonRenderRef,
    CanonSourceRef,
)
from novelforge.story_engine.canon.repository import CanonRepository
from novelforge.story_engine.canon.validator import SourceReferenceValidator


def _repo(tmp_path) -> CanonRepository:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_fact(CanonFact(
        fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN", canonical_key="ZERO_LAYER_GATE_FIRST_OPEN",
        novel_id="n1", status="happened", canonical_description="第一次打开第零层门禁",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_gate_open",
                                    chapter_uuid="uuid_gate_open", source_id="uuid_gate_open")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate_open", display_number=318)))
    repo.save_fact(CanonFact(
        fact_id="FACT_FUTURE_REVEAL", canonical_key="FUTURE_REVEAL", novel_id="n1",
        status="planned", canonical_description="未来才揭示的真相",
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_future", display_number=500)))
    repo.save_knowledge(CanonKnowledge(
        knowledge_id="KNW_HERO", novel_id="n1", fact_id="FACT_ZERO_LAYER_GATE_FIRST_OPEN",
        holder_id="protagonist", state="known", learned_at=300, learned_from="witness"))
    return repo


def test_wrong_chapter_cannot_support_fact(tmp_path) -> None:
    """产品级等价于「把伏击章当成第零层开门」：必须被检出。"""

    repo = _repo(tmp_path)
    validator = SourceReferenceValidator(repo)
    report = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="chapter", source_uuid="uuid_ambush", chapter_uuid="uuid_ambush",
        claimed_fact_ids=["FACT_ZERO_LAYER_GATE_FIRST_OPEN"], provenance="happened")])
    codes = {f.code for f in report.findings}
    assert "SOURCE_REF_SEMANTIC_MISMATCH" in codes
    assert report.source_ref_semantic_mismatch_count == 1
    assert report.ok() is False
    repo.close()


def test_missing_fact_and_future_leak(tmp_path) -> None:
    repo = _repo(tmp_path)
    validator = SourceReferenceValidator(repo)
    report = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="outline", source_uuid="uuid_gate_open", chapter_uuid="uuid_gate_open",
        claimed_fact_ids=["FACT_NOT_EXIST"])])
    assert report.source_ref_missing_count == 1
    future = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="outline", source_uuid="uuid_future", chapter_uuid="uuid_future",
        claimed_fact_ids=["FACT_FUTURE_REVEAL"])], temporal_cutoff=200)
    assert future.source_ref_future_leak_count == 1
    repo.close()


def test_status_and_scope_mismatch(tmp_path) -> None:
    repo = _repo(tmp_path)
    validator = SourceReferenceValidator(repo)
    status = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="outline", source_uuid="uuid_future", chapter_uuid="uuid_future",
        claimed_fact_ids=["FACT_FUTURE_REVEAL"], provenance="happened")])
    assert status.source_ref_status_mismatch_count == 1
    scope = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="outline", source_uuid="uuid_future", chapter_uuid="uuid_future",
        claimed_fact_ids=["FACT_FUTURE_REVEAL"])], character_scope="npc_2")
    assert scope.source_ref_scope_mismatch_count == 1
    repo.close()


def test_correct_reference_passes(tmp_path) -> None:
    repo = _repo(tmp_path)
    validator = SourceReferenceValidator(repo)
    report = validator.validate_refs("n1", refs=[CanonSourceRef(
        source_type="chapter", source_uuid="uuid_gate_open", chapter_uuid="uuid_gate_open",
        claimed_fact_ids=["FACT_ZERO_LAYER_GATE_FIRST_OPEN"], provenance="happened")],
        temporal_cutoff=400)
    assert report.ok() is True
    repo.close()


def test_promotion_conflict_is_reported_not_merged(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.save_event(CanonEvent(event_id="EVENT_RAIDER_FIRST_TOLL", canonical_key="RAIDER_FIRST_TOLL",
                               novel_id="n1", canonical_name="掠夺队第一次收过路费",
                               semantic_summary="第一次勒索", event_type="major", status="planned",
                               location="salt_road", subjects=["raiders", "settlement"]))
    repo.save_event(CanonEvent(event_id="EVENT_RAIDER_TOLL_OCCURRED",
                               canonical_key="RAIDER_TOLL_OCCURRED", novel_id="n1",
                               canonical_name="掠夺队收过路费", semantic_summary="实际发生",
                               event_type="major", status="occurred", location="salt_road",
                               subjects=["raiders", "settlement"]))
    validator = SourceReferenceValidator(repo)
    conflicts = validator.promotion_conflicts("n1")
    assert len(conflicts) == 1 and conflicts[0].code == "PROMOTION_CONFLICT"
    repo.close()
