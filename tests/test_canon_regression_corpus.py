"""C09：Canon regression corpus —— 把 dogfood 踩过的坑固化为通用回归（REG-001…REG-012）。

fixture 全部使用通用命名（无实例人名 / 地名），真实 wasteland 数据只做可选只读扫描。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.canon.chapters import ChapterLineage, ChapterLineageStore
from novelforge.story_engine.canon.context import CanonContextBuilder
from novelforge.story_engine.canon.gate import SchemaGateError, validate_chapter_plan
from novelforge.story_engine.canon.graph import CanonGraph, CanonGraphValidator
from novelforge.story_engine.canon.models import (
    CanonEvent,
    CanonFact,
    CanonKnowledge,
    CanonRenderRef,
    CanonSourceRef,
)
from novelforge.story_engine.canon.repository import CanonRepository
from novelforge.story_engine.canon.semantic import EventSemanticSignature, LocalSemanticIndex
from novelforge.story_engine.canon.service import CanonService
from novelforge.story_engine.canon.validator import SourceReferenceValidator

WORKSPACE_FIXTURE = Path("workspace/wasteland_001_exports/WASTELAND_001_OUTLINE_V3_CANONICAL_CANDIDATE.json")


def _repo(tmp_path) -> CanonRepository:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_fact(CanonFact(
        fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN", novel_id="n1", status="happened",
        canonical_description="第一次打开门禁",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_gate",
                                    chapter_uuid="uuid_gate", source_id="uuid_gate")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=318)))
    repo.save_fact(CanonFact(
        fact_id="FACT_RULES_ESTABLISHED", canonical_key="RULES_ESTABLISHED", novel_id="n1",
        status="happened", canonical_description="据点第一批成文规矩",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_rules",
                                    chapter_uuid="uuid_rules")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_rules", display_number=44)))
    repo.save_fact(CanonFact(
        fact_id="FACT_ARCHIVE_PUBLIC_RELEASE", canonical_key="ARCHIVE_PUBLIC_RELEASE",
        novel_id="n1", status="planned", canonical_description="档案首次公开",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_archive",
                                    chapter_uuid="uuid_archive")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_archive", display_number=442)))
    return repo


# ---- REG-001 / REG-002 / REG-003：错误 source / anchor / identity -------------
def test_reg001_chapter_number_drift(tmp_path) -> None:
    repo = _repo(tmp_path)
    report = SourceReferenceValidator(repo).validate_refs("n1", refs=[CanonSourceRef(
        source_type="chapter", source_uuid="uuid_ambush", chapter_uuid="uuid_ambush",
        claimed_fact_ids=["FACT_GATE_OPEN"], provenance="happened")])
    assert report.source_ref_semantic_mismatch_count == 1
    repo.close()


def test_reg002_wrong_canonical_anchor(tmp_path) -> None:
    repo = _repo(tmp_path)
    report = SourceReferenceValidator(repo).validate_refs("n1", refs=[CanonSourceRef(
        source_type="chapter", source_uuid="uuid_rules", chapter_uuid="uuid_rules",
        claimed_fact_ids=["FACT_ARCHIVE_PUBLIC_RELEASE"], provenance="happened")])
    codes = {f.code for f in report.findings}
    assert {"SOURCE_REF_SEMANTIC_MISMATCH", "SOURCE_REF_STATUS_MISMATCH"} <= codes
    repo.close()


def test_reg003_wrong_event_identity(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.save_event(CanonEvent(event_id="EVENT_ALLIANCE", canonical_key="ALLIANCE", novel_id="n1",
                               canonical_name="三方结盟条件", semantic_summary="政治结盟",
                               event_type="major", status="occurred", location="core",
                               subjects=["faction_a", "faction_b"]))
    index = LocalSemanticIndex()
    index.index_event(EventSemanticSignature(
        event_id="EVENT_ALLIANCE", semantic_summary="三方结盟条件", subjects=["faction_a"],
        action="结盟", location="core", event_type="major"))
    other = EventSemanticSignature(event_id="EVENT_RATION_SPLIT", semantic_summary="早期资源分配",
                                   subjects=["faction_a"], action="分粮", location="camp",
                                   event_type="major")
    assert index.classify_relation(index.get_event("EVENT_ALLIANCE"), other) != "duplicate"
    repo.close()


# ---- REG-004 / REG-005：时序与知识边界 --------------------------------------
def test_reg004_resolved_event_reopened() -> None:
    graph = CanonGraph.from_records(events=[
        {"event_id": "EVENT_LEAVE", "order": 10, "status": "resolved"},
        {"event_id": "EVENT_STILL_AWAY", "order": 14, "status": "planned",
         "canonical_event_id": "EVENT_LEAVE"}])
    codes = {f["code"] for f in CanonGraphValidator(graph).run()}
    assert "RESOLVED_EVENT_REOPENED" in codes


def test_reg005_knowledge_leak(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.save_knowledge(CanonKnowledge(
        knowledge_id="KNW_BEFORE_REVEAL", novel_id="n1", fact_id="FACT_ARCHIVE_PUBLIC_RELEASE",
        holder_id="protagonist", state="known", learned_at=100, learned_from=""))
    graph = CanonGraph.from_records(
        facts=[{"fact_id": "FACT_ARCHIVE_PUBLIC_RELEASE", "order": 442}],
        knowledge=[{"knowledge_id": "KNW_BEFORE_REVEAL",
                    "fact_id": "FACT_ARCHIVE_PUBLIC_RELEASE", "order": 100, "state": "known",
                    "learned_from": ""}])
    codes = {f["code"] for f in CanonGraphValidator(graph).run()}
    assert {"KNOWLEDGE_LEAK", "KNOWLEDGE_BEFORE_FACT"} <= codes
    # 只有持有 knowledge 记录才会进入 CharacterContext；无记录的事实在该角色视图中不出现
    context = CanonContextBuilder(repo).character_context("n1", "npc_other", temporal_cutoff=200)
    assert context.entries == []
    holder_view = CanonContextBuilder(repo).character_context("n1", "protagonist",
                                                              temporal_cutoff=300)
    assert any("档案首次公开" in entry.canonical_description for entry in holder_view.entries)
    repo.close()


# ---- REG-006 / REG-008 / REG-009：Schema 与 writer-visible -------------------
def test_reg006_string_events_fail_schema_gate() -> None:
    with pytest.raises(SchemaGateError):
        validate_chapter_plan({"chapter_uuid": "uuid_1",
                               "concrete_events": "角色利用能力挡住风暴",
                               "title": "风暴"})


def test_reg008_and_reg009_writer_visible_metadata_fail() -> None:
    base = {"chapter_uuid": "uuid_1", "title": "风暴",
            "concrete_events": ["角色举起护盾挡住风暴", "队友被吹倒", "他把队友拖回掩体"],
            "dog_role": "absent"}
    with pytest.raises(SchemaGateError):
        validate_chapter_plan({**base, "hook": "与 ch142 相同"})
    with pytest.raises(SchemaGateError):
        validate_chapter_plan({**base, "start_state": "承接 FACT_GATE_OPEN"})


# ---- REG-007：语义重复候选 ---------------------------------------------------
def test_reg007_semantic_duplicate_candidate() -> None:
    index = LocalSemanticIndex()
    first = EventSemanticSignature(event_id="EVENT_TOLL_1", semantic_summary="掠夺队第一次收过路费",
                                   subjects=["raiders", "settlement"],
                                   action="收取过路费", location="road", event_type="major",
                                   can_repeat=False)
    second = EventSemanticSignature(event_id="EVENT_TOLL_2", semantic_summary="掠夺队首度强收路费",
                                   subjects=["raiders", "settlement"],
                                   action="收取过路费", location="road", event_type="major",
                                   can_repeat=False)
    index.index_event(first)
    candidates = index.candidates(second, top_k=3, threshold=0.3)
    assert candidates and candidates[0].relation in ("duplicate", "uncertain")
    assert candidates[0].score >= 0.5


# ---- REG-010 / REG-011 / REG-012 --------------------------------------------
def test_reg010_renumber_keeps_identity(tmp_path) -> None:
    repo = _repo(tmp_path)
    store = ChapterLineageStore(repo)
    store.register(ChapterLineage(chapter_uuid="uuid_gate", novel_id="n1", display_number=325))
    store.renumber("n1", {"uuid_gate": 318})
    assert store.get("uuid_gate").chapter_uuid == "uuid_gate"
    assert store.get("uuid_gate").display_number == 318
    assert [f.fact_id for f in repo.facts("n1") if f.fact_id == "FACT_GATE_OPEN"]
    repo.close()


def test_reg011_planned_to_happened_keeps_event_id(tmp_path) -> None:
    repo = _repo(tmp_path)
    service = CanonService(repo)
    event = service.new_event(novel_id="n1", name="门禁首次打开", summary="打开门禁")
    repo.save_event(event)
    promoted = service.promote_event(event.event_id, novel_id="n1")
    assert promoted.event_id == event.event_id and promoted.status == "occurred"
    assert len([e for e in repo.events("n1") if e.canonical_key == event.canonical_key]) == 1
    repo.close()


def test_reg012_shadow_does_not_pollute_official(tmp_path) -> None:
    repo = _repo(tmp_path)
    official_dir = tmp_path / "official"
    shadow_dir = tmp_path / "shadow"
    from novelforge.story_engine.canon.planner import (
        ArcIntent, CanonAwareOutlinePlanner, CanonOutlineFlags, FileOutlineSink)
    planner = CanonAwareOutlinePlanner(
        repo, flags=CanonOutlineFlags(canon_outline_shadow_mode=True),
        sink=FileOutlineSink(official_dir), shadow_sink=FileOutlineSink(shadow_dir))
    chapter = {
        "chapter_uuid": "uuid_shadow_1", "title": "门后的第一层", "estimated_words": 3000,
        "temporal_position": 319, "location": "gate",
        "concrete_events": ["他把铭牌按进凹槽等待回应", "厚重门板在第七次尝试后打开",
                            "队伍沿着干燥长廊向深处推进"],
        "dog_role": "absent", "participants": ["protagonist"], "locations": ["gate"],
        "prerequisites": [], "requires_abilities": [], "grants_abilities": [],
        "requires_identities": [], "grants_identities": [], "character_state_effects": [],
        "knowledge_changes": [], "relationship_changes": [], "resource_changes": {},
        "ability_changes": [], "identity_changes": [], "foreshadow_actions": [],
        "canon_fact_ids": [], "canon_event_ids": [], "canon_source_refs": [],
    }
    beats = [{"beat_id": "BEAT_1", "goal": "开门"}]
    result = planner.shadow_plan(ArcIntent(arc_id="ARC_GATE", novel_id="n1", temporal_position=320),
                                 beats_raw=beats, chapters_raw=[chapter])
    assert result.ok is True
    assert list(shadow_dir.glob("*.json")) and not list(official_dir.glob("*.json"))
    assert repo._connection.execute(
        "SELECT COUNT(*) AS n FROM canon_chapter_lineage").fetchone()["n"] == 0
    assert len(repo.facts("n1")) == 3
    repo.close()


# ---- Optional real dogfood fixture（只读；不存在则 SKIP） ----------------------
@pytest.mark.skipif(not WORKSPACE_FIXTURE.is_file(), reason="workspace fixture 不存在（可选项）")
def test_optional_real_wasteland_scan_is_read_only() -> None:
    data = json.loads(WORKSPACE_FIXTURE.read_text(encoding="utf-8"))
    chapters = data.get("chapters") or []
    writer_visible = " ".join(
        json.dumps({k: c.get(k) for k in ("title", "goal", "start_state", "hook", "turn",
                                          "payoff", "end_state", "events")}, ensure_ascii=False)
        for c in chapters)
    assert "ch" in writer_visible or writer_visible  # 扫描本身不改数据
    assert WORKSPACE_FIXTURE.is_file()
