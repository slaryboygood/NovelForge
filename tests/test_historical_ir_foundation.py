"""P15f：Historical Full Chapter Semantic IR Foundation 回归。

覆盖：source inventory / full ChapterSemanticIR schema / historical time_layer /
stable chapter uuid / deterministic ids / N-A vs unresolved / 不发明 decision-turn-payoff /
knowledge boundary / relationship-resource-progression-location continuity /
causality unresolved / artifact idempotency / checkpoint-resume / repair replay /
44 human review 重评 / Canon-StoryState-source 不变 / M11 overlay 未被覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.chapter_ir.models import ChapterSemanticIR
from novelforge.story_engine.historical_ir import (
    HistoricalIRFoundationService,
    HistoricalIRMaterializer,
    digest_file,
    digest_payload,
)

ROOT = Path(".").resolve()
REPAIR_OVERLAY = ROOT / "workspace/wasteland_001_exports/repair_v1/M11_OVERLAY.json"


@pytest.fixture(scope="module")
def foundation(tmp_path_factory: pytest.TempPathFactory):
    store = tmp_path_factory.mktemp("historical_ir") / "store"
    service = HistoricalIRFoundationService(ROOT, store_dir=str(store))
    payload = service.run(resume=True)
    return service, payload


def _artifact(service: HistoricalIRFoundationService, name: str):
    return json.loads((service.store_dir / name).read_text(encoding="utf-8"))


def test_source_inventory_570_coverage(foundation) -> None:
    service, _payload = foundation
    inventory = _artifact(service, "SOURCE_INVENTORY.json")
    assert inventory["chapter_count"] == 570
    assert inventory["channel_availability"]["legacy_outline"] == 570
    assert inventory["channel_availability"]["prose_text"] == 0
    assert inventory["counts"]["evidence_completeness_SUFFICIENT"] == 570
    assert all(row["legacy_fields_digest"] for row in inventory["rows"])
    assert "legacy outline record" in inventory["prose_note"]


def test_full_chapter_semantic_ir_schema_and_time_layer(foundation) -> None:
    service, _payload = foundation
    artifacts = service.store.load_artifacts()
    assert len(artifacts) == 570
    for chapter_id, artifact in artifacts.items():
        assert artifact.time_layer == "happened_historical"
        assert artifact.derived is True
        assert artifact.canonical_representation is False
        assert artifact.non_authoritative is True
        body = ChapterSemanticIR.model_validate(artifact.chapter_ir.model_dump(mode="json"))
        assert body.chapter_uuid == chapter_id
        assert artifact.chapter_ir_digest == digest_payload(
            artifact.chapter_ir.model_dump(mode="json"))
        assert artifact.assertion("turn") is not None


def test_stable_chapter_uuid_and_deterministic_ids(foundation) -> None:
    service, _payload = foundation
    materializer = service.materializer
    inputs = materializer.load()
    expected = {str(row.get("chapter_uuid")) for row in inputs.chapters}
    artifacts = service.store.load_artifacts()
    assert set(artifacts) == expected
    chapter = inputs.chapters[0]
    first = materializer.materialize_chapter(chapter, inputs, created_at="fixed")
    second = materializer.materialize_chapter(chapter, inputs, created_at="fixed")
    assert first.chapter_ir_digest == second.chapter_ir_digest
    assert [item.event_id for item in first.chapter_ir.event_frames] == \
        [item.event_id for item in second.chapter_ir.event_frames]
    assert all(item.event_id.startswith("CE_") for item in first.chapter_ir.event_frames)


def test_na_vs_unresolved_semantics(foundation) -> None:
    service, _payload = foundation
    materializer = service.materializer
    inputs = materializer.load()
    chapter = inputs.chapters[0]
    artifact = materializer.materialize_chapter(chapter, inputs, created_at="fixed")
    cost = artifact.assertion("cost")
    assert cost is not None and cost.assertion_mode == "UNRESOLVED"
    assert cost.reason.startswith("legacy cost 有文本但无 negative effect")
    for field_name in ("resource", "progression"):
        assertion = artifact.assertion(field_name)
        assert assertion is not None and assertion.assertion_mode == "NOT_APPLICABLE"
    assert "decision" in artifact.unresolved_fields


def test_no_invented_decision_turn_payoff(foundation) -> None:
    service, _payload = foundation
    materializer = service.materializer
    inputs = materializer.load()
    for artifact in service.store.load_artifacts().values():
        decision = artifact.assertion("decision")
        assert decision is not None
        if decision.assertion_mode == "DIRECT_SOURCE":
            assert [item for item in artifact.chapter_ir.event_frames
                    if item.decision_action]
        turn = artifact.assertion("turn")
        assert turn is not None
        if turn.assertion_mode in ("DIRECT_SOURCE", "DERIVED"):
            assert turn.bound_ir_ids
        payoff = artifact.assertion("payoff")
        assert payoff is not None
        if payoff.assertion_mode == "DIRECT_SOURCE":
            assert [item for item in artifact.chapter_ir.effects
                    if item.polarity in ("positive", "mixed")]
    placeholder_rows = [row for row in inputs.chapters
                        if str(row.get("decision") or "").startswith("按本章做法处理")]
    assert placeholder_rows
    placeholder_ids = {str(row["chapter_uuid"]) for row in placeholder_rows}
    artifacts = service.store.load_artifacts()
    for chapter_id in placeholder_ids:
        decision = artifacts[chapter_id].assertion("decision")
        assert decision.assertion_mode != "DIRECT_SOURCE"


def test_canon_refs_recorded_without_confirmed_claims(foundation) -> None:
    service, _payload = foundation
    inventory = _artifact(service, "SOURCE_INVENTORY.json")
    labelled = {row["legacy_label"]: row for row in inventory["rows"]}
    assert labelled["ch005"]["canon_refs"] == ["FACT_RADIO_FIRST_RESPONSE"]
    for artifact in service.store.load_artifacts().values():
        assert all(item.assertion_mode != "CONFIRMED"
                   for item in artifact.field_assertions)


def test_knowledge_boundary_not_invented(foundation) -> None:
    service, _payload = foundation
    unresolved = 0
    for artifact in service.store.load_artifacts().values():
        assertion = artifact.assertion("knowledge")
        assert assertion is not None
        assert assertion.assertion_mode != "DIRECT_SOURCE"
        unresolved += int(assertion.assertion_mode == "UNRESOLVED")
    assert unresolved > 0


def test_relationship_resource_progression_continuity(foundation) -> None:
    service, _payload = foundation
    materializer = service.materializer
    inputs = materializer.load()
    chapters = {str(row["chapter_uuid"]): row for row in inputs.chapters}
    for chapter_id, artifact in service.store.load_artifacts().items():
        row = chapters[chapter_id]
        for field_name, legacy_name in (("relationship", "relationship_delta"),
                                        ("resource", "resource_delta"),
                                        ("progression", "ability_delta")):
            assertion = artifact.assertion(field_name)
            assert assertion is not None
            legacy = row.get(legacy_name)
            has_delta = bool(legacy) and (
                any(str(item).strip() not in ("", "0") for item in legacy.values())
                if isinstance(legacy, dict) else str(legacy).strip() not in ("", "无"))
            if has_delta:
                assert assertion.assertion_mode == "DIRECT_SOURCE"
            else:
                assert assertion.assertion_mode == "NOT_APPLICABLE"


def test_location_and_causality_rules(foundation) -> None:
    service, _payload = foundation
    materializer = service.materializer
    inputs = materializer.load()
    chapters = {str(row["chapter_uuid"]): row for row in inputs.chapters}
    map_names = set(materializer.map_names())
    causality_unresolved = 0
    for chapter_id, artifact in service.store.load_artifacts().items():
        location = artifact.assertion("location")
        assert location is not None
        if location.assertion_mode == "DIRECT_SOURCE":
            quotes = {ref.quote for ref in location.evidence_refs}
            assert quotes & map_names
        causality = artifact.assertion("causality")
        assert causality is not None
        if causality.assertion_mode == "DERIVED":
            assert str(chapters[chapter_id].get("next_chapter_causality") or "").strip()
        else:
            causality_unresolved += 1
    assert causality_unresolved > 0      # §23：允许 causality unresolved


def test_artifact_idempotency_and_no_duplicate(foundation) -> None:
    service, _payload = foundation
    before_index = _artifact(service, "index.json")
    before_files = sorted(path.name for path in service.store.artifacts_dir.glob("*.json"))
    payload = service.run(resume=True)
    after_index = _artifact(service, "index.json")
    after_files = sorted(path.name for path in service.store.artifacts_dir.glob("*.json"))
    assert payload["report"]["reused_artifacts"] == 570
    assert before_index["index_digest"] == after_index["index_digest"]
    assert before_files == after_files and len(after_files) == 570


def test_checkpoint_resume_rebuilds_missing_artifact(foundation) -> None:
    service, _payload = foundation
    checkpoint = _artifact(service, "checkpoint.json")
    assert checkpoint["total"] == 570 and checkpoint["status"] == "COMPLETE"
    victim = sorted(service.store.artifacts_dir.glob("*.json"))[0]
    victim.unlink()
    service.run(resume=True)
    assert victim.is_file()
    assert len(list(service.store.artifacts_dir.glob("*.json"))) == 570
    index = _artifact(service, "index.json")
    assert index["chapter_count"] == 570


def test_repair_replay_clean_and_obsolete_detection(foundation) -> None:
    service, payload = foundation
    replay = _artifact(service, "REPAIR_REPLAY.json")
    assert replay["repair_count"] == 20
    assert replay["dry_run"] is True and replay["canonicalized"] is False
    statuses = replay["status_counts"]
    assert statuses.get("CONFLICT", 0) == 0
    assert statuses.get("HUMAN_REVIEW", 0) == 0
    assert statuses.get("APPLIES_CLEANLY", 0) + statuses.get("OBSOLETE_REPAIR", 0) == 20
    rows = {row["legacy_label"]: row for row in replay["results"]}
    assert rows["ch055"]["status"] == "OBSOLETE_REPAIR"      # base IR 已自带 pivot
    assert rows["ch011"]["status"] == "APPLIES_CLEANLY"
    assert all(row["forbidden_change_violation"] is False for row in replay["results"])
    assert payload["evidence_sufficiency_after_foundation"]["status"] == \
        "SUFFICIENT_TO_CONTINUE"


def test_human_review_reevaluation_44(foundation) -> None:
    service, _payload = foundation
    reevaluation = _artifact(service, "HUMAN_REVIEW_REEVALUATION.json")
    assert reevaluation["human_review_count"] == 44
    assert reevaluation["overlay_modified"] is False
    assert reevaluation["class_counts"] == {
        "TRULY_MISSING": 36, "EVIDENCE_ONLY": 6,
        "AUTHOR_DECISION_REQUIRED": 1, "FIELD_REBIND": 1}
    rows = {row["legacy_label"]: row for row in reevaluation["rows"]}
    assert rows["ch036"]["proposed_class"] == "AUTHOR_DECISION_REQUIRED"
    assert rows["ch063"]["proposed_class"] == "FIELD_REBIND"
    assert rows["ch008"]["proposed_class"] == "EVIDENCE_ONLY"
    assert rows["ch015"]["proposed_class"] == "TRULY_MISSING"
    assert all(row["previous_reason"] in ("SOURCE_IR_INSUFFICIENT",
                                          "AUTHOR_INTENT_REQUIRED", "")
               for row in reevaluation["rows"])


def test_overlay_not_overwritten_and_truth_digests_unchanged(foundation) -> None:
    service, payload = foundation
    before = digest_file(REPAIR_OVERLAY)
    official = json.loads(REPAIR_OVERLAY.read_text(encoding="utf-8"))
    payload_again = service.run(resume=True)
    assert digest_file(REPAIR_OVERLAY) == before
    # P15f 只读正式 overlay：digest 在 foundation 运行前后不变（P15g 才正式更新语义）
    assert official["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                                "LEGACY_FIELD_CONFLICT": 27,
                                                "LEGACY_CONTENT_GAP": 345}
    assert official["resolved_total"] >= 20
    digests = payload_again["evidence_sufficiency_after_foundation"]
    assert digests["previous_status"] == "FULL_IR_FOUNDATION_REQUIRED"
    report = payload_again["report"]
    assert report["source_digests"]["unchanged"] is True
    assert report["llm_used"] is False


def test_foundation_gate_ready(foundation) -> None:
    service, payload = foundation
    gate = _artifact(service, "HISTORICAL_IR_FOUNDATION_GATE.json")
    assert gate["status"] == "READY"
    assert all(gate["checks"].values()), [k for k, v in gate["checks"].items() if not v]
    assert gate["chapter_count"] == 570
    assert gate["source_digests"]["before"] == gate["source_digests"]["after"]
    assert payload["HISTORICAL_IR_FOUNDATION_STATUS"] == "READY"
    manifest = _artifact(service, "manifest.json")
    assert manifest["chapter_count"] == 570 and manifest["llm_used"] is False
    assert manifest["canonical_representation"] is False
    integrity = _artifact(service, "integrity.json")
    assert integrity["all_digests_stable"] is True


def test_golden_chapter_regression(foundation) -> None:
    service, _payload = foundation
    golden = _artifact(service, "GOLDEN_CHAPTER_REGRESSION.json")
    assert golden["status"] == "PASS"
    assert golden["foundation_golden"]["total"] == 20
    assert golden["foundation_golden"]["matched"] == 20
    assert golden["llm_used"] is False
    # M1 fixture golden：deterministic-only 与 LLM-adopted 标签的差集必须显式登记
    assert golden["m1_golden"]["total"] == 35
    assert golden["m1_golden"]["matched"] == 25
    labels = {row["legacy_label"] for row in golden["m1_golden"]["deltas"]}
    assert labels == {"ch506", "ch271", "ch325", "ch379", "ch436", "ch449", "ch502",
                      "ch515", "ch526", "ch559"}
    assert all(row["problems"] for row in golden["m1_golden"]["deltas"])
