"""C07：CanonAwareOutlinePlanner（flag / gate / graph / source ref / lineage / shadow）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.canon.chapters import ChapterLineage, ChapterLineageStore
from novelforge.story_engine.canon.models import CanonFact, CanonRenderRef, CanonSourceRef
from novelforge.story_engine.canon.planner import (
    ArcIntent,
    CanonAwareOutlinePlanner,
    CanonOutlineFlags,
    FileOutlineSink,
)
from novelforge.story_engine.canon.repository import CanonRepository


def _repo(tmp_path) -> CanonRepository:
    repo = CanonRepository(tmp_path / "canon.sqlite")
    repo.save_fact(CanonFact(
        fact_id="FACT_GATE_OPEN", canonical_key="GATE_OPEN", novel_id="n1", status="happened",
        canonical_description="第一次打开门禁",
        source_refs=[CanonSourceRef(source_type="chapter", source_uuid="uuid_gate",
                                    chapter_uuid="uuid_gate", source_id="uuid_gate")],
        first_occurrence_ref=CanonRenderRef(chapter_uuid="uuid_gate", display_number=10)))
    return repo


def _beat(**overrides) -> dict:
    base = {"beat_id": "BEAT_1", "goal": "打开门禁", "event_ids": ["EVENT_GATE_OPEN"],
            "fact_ids": ["FACT_GATE_OPEN"], "participant_ids": ["protagonist"],
            "location_ids": ["location_gate"]}
    base.update(overrides)
    return base


def _chapter(**overrides) -> dict:
    base = {
        "chapter_uuid": "uuid_ch_1", "display_number": 245, "title": "门后的第一层",
        "estimated_words": 3200, "temporal_position": 245, "location": "location_gate",
        "goal": "打开门禁并确认门后环境", "start_state": "队伍带齐装备站在门前",
        "concrete_events": ["韩彻把铭牌按进凹槽", "门在第七次尝试后打开", "队伍沿干燥长廊深入"],
        "dog_role": "involved", "dog_action": "阿灰在门前贴地判断震动方向",
        "canon_fact_ids": ["FACT_GATE_OPEN"], "canon_event_ids": [],
        "canon_source_refs": [{"source_type": "chapter", "source_uuid": "uuid_gate",
                               "chapter_uuid": "uuid_gate",
                               "claimed_fact_ids": ["FACT_GATE_OPEN"],
                               "provenance": "happened"}],
        "participants": ["protagonist"], "locations": ["location_gate"],
        "prerequisites": [], "requires_abilities": [], "grants_abilities": [],
        "requires_identities": [], "grants_identities": [],
        "character_state_effects": [], "knowledge_changes": [], "relationship_changes": [],
        "resource_changes": {}, "ability_changes": [], "identity_changes": [],
        "foreshadow_actions": [], "hook": "长廊尽头传来第二种脚步",
    }
    base.update(overrides)
    return base


def _intent() -> ArcIntent:
    return ArcIntent(arc_id="ARC_GATE", novel_id="n1", goal="进入第零层", volume_ref="V7",
                     participant_ids=["protagonist"], location_ids=["location_gate"],
                     temporal_position=250)


def test_flag_off_keeps_legacy_behaviour(tmp_path) -> None:
    repo = _repo(tmp_path)
    planner = CanonAwareOutlinePlanner(repo, flags=CanonOutlineFlags())
    assert planner.should_use_canon_path() is False
    repo.close()


def test_flag_on_runs_pipeline_and_records_manifest(tmp_path) -> None:
    repo = _repo(tmp_path)
    sink = FileOutlineSink(tmp_path / "out")
    planner = CanonAwareOutlinePlanner(repo, flags=CanonOutlineFlags(canon_outline_v1=True),
                                       sink=sink)
    result = planner.plan(_intent(), beats_raw=[_beat()], chapters_raw=[_chapter()])
    assert result.ok is True
    assert result.chapter_uuids == ["uuid_ch_1"]
    assert result.context_manifest_id.startswith("CTX_")
    assert Path(result.persisted_path).is_file()
    row = repo._connection.execute(
        "SELECT payload FROM canon_context_manifests WHERE context_id = ?",
        (result.context_manifest_id,)).fetchone()
    assert row is not None and "included_fact_ids" in row["payload"]
    repo.close()


def test_invalid_schema_missing_metadata_and_bad_source_do_not_persist(tmp_path) -> None:
    repo = _repo(tmp_path)
    sink = FileOutlineSink(tmp_path / "out")
    planner = CanonAwareOutlinePlanner(repo, sink=sink)

    bad_schema = planner.plan(_intent(), beats_raw=[_beat()],
                              chapters_raw=[_chapter(concrete_events="韩彻打开门禁")])
    assert bad_schema.ok is False
    assert any(f.code == "CHAPTER_SCHEMA_INVALID" for f in bad_schema.findings)

    missing = _chapter()
    missing.pop("temporal_position")
    bad_metadata = planner.plan(_intent(), beats_raw=[_beat()], chapters_raw=[missing])
    assert bad_metadata.ok is False
    assert any(f.code == "GRAPH_METADATA_MISSING" for f in bad_metadata.findings)

    bad_source = planner.plan(_intent(), beats_raw=[_beat()], chapters_raw=[_chapter(
        canon_source_refs=[{"source_type": "chapter", "source_uuid": "uuid_ambush",
                            "chapter_uuid": "uuid_ambush",
                            "claimed_fact_ids": ["FACT_GATE_OPEN"],
                            "provenance": "happened"}])])
    assert bad_source.ok is False
    assert any(f.code == "SOURCE_REF_SEMANTIC_MISMATCH" for f in bad_source.findings)
    assert not list((tmp_path / "out").glob("*.json"))
    repo.close()


def test_writer_visible_metadata_and_happened_rewrite_are_blocked(tmp_path) -> None:
    repo = _repo(tmp_path)
    planner = CanonAwareOutlinePlanner(repo)
    leak = planner.plan(_intent(), beats_raw=[_beat()],
                        chapters_raw=[_chapter(hook="与 ch142 相同")])
    assert leak.ok is False and any(f.code in ("CHAPTER_SCHEMA_INVALID",
                                               "WRITER_VISIBLE_METADATA_LEAK")
                                    for f in leak.findings)
    rewrite = planner.plan(_intent(), beats_raw=[_beat()],
                           chapters_raw=[_chapter(temporal_position=3)])
    assert rewrite.ok is False
    assert any(f.code == "HAPPENED_FACT_REWRITE" for f in rewrite.findings)
    repo.close()


def test_chapter_uuid_survives_renumber_and_lineage_split_merge(tmp_path) -> None:
    repo = _repo(tmp_path)
    store = ChapterLineageStore(repo)
    store.register(ChapterLineage(chapter_uuid="uuid_a", novel_id="n1", display_number=325,
                                  title="门禁"))
    assert store.renumber("n1", {"uuid_a": 318}) == 1
    assert store.get("uuid_a").display_number == 318
    first, second = store.split("uuid_a", novel_id="n1")
    assert store.get("uuid_a").status == "superseded"
    assert store.get("uuid_a").superseded_by == [first, second]
    marker = _chapter(chapter_uuid="uuid_m1")
    store.register(ChapterLineage(chapter_uuid="uuid_m1", novel_id="n1"))
    store.register(ChapterLineage(chapter_uuid="uuid_m2", novel_id="n1"))
    merged = store.merge(["uuid_m1", "uuid_m2"], novel_id="n1", title="合并章")
    assert store.get("uuid_m1").status == "merged"
    assert store.get("uuid_m1").merged_into == merged
    assert marker is not None
    repo.close()


def test_shadow_mode_is_isolated(tmp_path) -> None:
    repo = _repo(tmp_path)
    official = FileOutlineSink(tmp_path / "official")
    shadow = FileOutlineSink(tmp_path / "shadow")
    planner = CanonAwareOutlinePlanner(
        repo, flags=CanonOutlineFlags(canon_outline_shadow_mode=True), sink=official,
        shadow_sink=shadow)
    result = planner.shadow_plan(_intent(), beats_raw=[_beat()], chapters_raw=[_chapter()])
    assert result.ok is True and result.mode == "shadow"
    assert list(shadow.root.glob("*.json")) and not list(official.root.glob("*.json"))
    lineage = repo._connection.execute(
        "SELECT COUNT(*) AS n FROM canon_chapter_lineage").fetchone()
    assert lineage["n"] == 0          # shadow 不污染正式 Canon
    repo.close()
