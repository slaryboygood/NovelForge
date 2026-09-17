"""M10：WASTELAND Top-down Reconstruction 回归（只读分析，不修内容）。"""

from __future__ import annotations

import json
from pathlib import Path

from novelforge.story_engine.planning import PlanningRepository
from novelforge.story_engine.reconstruction import (
    CONTENT_GAP,
    CONFIRMED,
    CONFIRMED_SOURCES,
    FIELD_CONFLICT,
    WastelandReconstructionService,
)

ROOT = Path(".").resolve()
REQUIRED_ARTIFACTS = (
    "BASELINE.json", "HISTORICAL_STORY_MAP.json", "HISTORICAL_CAUSAL_SPINE.json",
    "STORY_HANDOFF_POINT.json", "OPEN_STORY_INVENTORY.json",
    "HISTORICAL_VOLUME_ALIGNMENT.json", "HISTORICAL_ARC_ALIGNMENT.json",
    "LEGACY_TARGET_ALIGNMENT.json", "REPAIR_QUEUE_RECLASSIFIED.json",
    "M11_BATCH_PLAN.json", "AUTHOR_DECISION_QUEUE.json",
    "FUTURE_STORY_SPINE_PROJECTION.json", "M10_FINAL_GATE.json")


def _run(tmp_path: Path):
    # 写入临时目录：service 支持绝对 recon_dir（只影响 M10 产物，不动 happened truth）
    service = WastelandReconstructionService(
        ROOT, recon_dir=str(tmp_path / "reconstruction_v2"))
    return service, service.run()


def _artifact(service: WastelandReconstructionService, name: str):
    return json.loads((service.recon_dir / name).read_text(encoding="utf-8"))


def test_baseline_counts_digests_and_gate(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    baseline, gate = summary["baseline"], summary["gate"]
    assert baseline.chapter_count == 570 and baseline.m1_coverage == 570
    assert baseline.queue_counts == {CONFIRMED: 198, FIELD_CONFLICT: 27, CONTENT_GAP: 345}
    assert all(len(item) == 16 for item in baseline.happened_digests().values())
    assert baseline.route_identity and baseline.content_pack_digest
    assert gate.ok() is True and gate.status == "PASS"
    assert gate.alignment_coverage == gate.chapter_total == 570
    assert gate.confirmed_chapters_in_repair == [] and gate.findings == []
    assert gate.happened_digests_before == gate.happened_digests_after
    assert gate.queue_counts_before == gate.queue_counts_after
    for name in REQUIRED_ARTIFACTS:
        assert (service.recon_dir / name).is_file(), name


def test_historical_map_time_layers_and_alignment_coverage(tmp_path: Path) -> None:
    service, _ = _run(tmp_path)
    story_map = _artifact(service, "HISTORICAL_STORY_MAP.json")
    assert len(story_map["chapters"]) == 570
    assert all(row["time_layer"] == "happened_historical" for row in story_map["chapters"])
    assert all(row["evidence_refs"] for row in story_map["chapters"])
    assert story_map["volumes"] and story_map["arcs"] and story_map["domain_counts"]
    handoff = _artifact(service, "STORY_HANDOFF_POINT.json")
    assert handoff["last_happened_label"] == "ch570"
    assert handoff["time_layer"] == "happened_historical"
    for key in ("current_character_state", "current_relationship_state",
                "current_faction_state", "current_location_state", "current_resources",
                "current_knowledge", "current_progression"):
        assert handoff[key], key
    assert handoff["next_feasible_opportunities"] and handoff["read_only"] is True


def test_target_alignment_reclassifies_conflicts_and_gaps(tmp_path: Path) -> None:
    service, _ = _run(tmp_path)
    target = _artifact(service, "LEGACY_TARGET_ALIGNMENT.json")
    targets = target["targets"]
    conflicts = [row for row in targets if row["current_classification"] == FIELD_CONFLICT]
    gaps = [row for row in targets if row["current_classification"] == CONTENT_GAP]
    assert len(conflicts) == 27 and len(gaps) == 345
    assert len(target["field_conflict_subtypes"]) >= 2
    assert len(target["content_gap_subtypes"]) >= 3
    assert sum(target["field_conflict_subtypes"].values()) == 27
    assert sum(target["content_gap_subtypes"].values()) == 345
    for row in targets:
        assert row["allowed_repair_types"] and row["evidence_refs"]
        assert row["forbidden_changes"] or row["required_context"]
        assert row["risk"] in ("LOW", "MEDIUM", "HIGH", "HUMAN_REQUIRED")
        assert row["time_layer"] == "legacy_representation"


def test_repair_batches_skip_confirmed_and_are_dependency_ordered(tmp_path: Path) -> None:
    service, _ = _run(tmp_path)
    story_map = _artifact(service, "HISTORICAL_STORY_MAP.json")
    confirmed = {row["chapter_id"] for row in story_map["chapters"]
                 if row["classification"] == CONFIRMED}
    assert len(confirmed) == 198
    plan = _artifact(service, "M11_BATCH_PLAN.json")
    batched = {chapter_id for batch in plan["batches"] for chapter_id in batch["chapter_ids"]}
    assert batched & confirmed == set() and len(batched) == 372
    for index, batch in enumerate(plan["batches"]):
        assert batch["dependency_batches"] == ([f"REPAIR_BATCH_{index:02d}"] if index else [])
        assert batch["acceptance"]["gates"] and batch["allowed_changes"]
        assert 1 <= len(batch["chapter_ids"]) <= 40


def test_author_decisions_are_localized_and_non_authoritative(tmp_path: Path) -> None:
    service, _ = _run(tmp_path)
    queue = _artifact(service, "AUTHOR_DECISION_QUEUE.json")
    assert queue["items"], "缺证据 / 歧义章节必须进入 AuthorDecisionQueue"
    for item in queue["items"]:
        assert item["blocking_scope"] == item["affected_arcs"]
        assert item["option_a"] and item["option_b"] and item["tradeoff"]
        assert item["recommended_default_is_authoritative"] is False
    assert "不必为 0" in queue["note"]


def test_future_planning_and_happened_truth_gate(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    repo = PlanningRepository(ROOT, "wasteland_001")
    assert repo.exists("PREV_WL_M10_FUTURE_1")
    plan = repo.load("PREV_WL_M10_FUTURE_1").plan
    assert plan.plot_nodes and plan.spine
    assert any(character.display_name.startswith("阿灰") for character in plan.characters)
    projection = _artifact(service, "FUTURE_STORY_SPINE_PROJECTION.json")
    assert projection["volume_targets"] and projection["arc_targets"]
    inventory = _artifact(service, "OPEN_STORY_INVENTORY.json")
    assert {"foreshadow", "mystery", "conflict", "map", "progression"} \
        <= set(inventory["by_domain"])
    baseline = summary["baseline"]
    after = service.baseline()
    assert baseline.happened_digests() == after.happened_digests()
    assert after.queue_counts == {CONFIRMED: 198, FIELD_CONFLICT: 27, CONTENT_GAP: 345}
    assert summary["gate"].status == "PASS"


def test_full_book_future_spine_covers_open_inventory(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    spine = _artifact(service, "FULL_BOOK_FUTURE_SPINE.json")
    inventory = _artifact(service, "OPEN_STORY_INVENTORY.json")
    assert spine["plan_node_count"] >= 20 and len(spine["major_node_ids"]) >= 4
    assert spine["volume_count"] >= 2 and spine["arc_count"] >= 2
    assert spine["remaining_target_words"] > 0 and spine["remaining_estimate_chapters"] >= 24
    assert not spine["undisposed_item_ids"]                 # 没有 open item 无声消失
    dispositions = {row["item_id"]: row["disposition"] for row in spine["item_dispositions"]}
    assert set(dispositions) == {item["item_id"] for item in inventory["items"]}
    assert set(dispositions.values()) <= {"scheduled", "deferred", "intentionally_unresolved",
                                          "terminal_resolution", "author_decision_required"}
    assert "chapter_ready" not in set(spine["detail_levels"].values())
    assert spine["conflict_escalation_chains"] and spine["relationship_arc_count"] >= 1
    assert spine["information_arc_count"] >= 1 and spine["foreshadow_path_count"] >= 1
    assert spine["time_layer"] == "future_planning"
    _ = summary


def test_structural_runway_report_and_route_respect(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    runway = _artifact(service, "STRUCTURAL_RUNWAY_REPORT.json")
    spine = _artifact(service, "FULL_BOOK_FUTURE_SPINE.json")
    assert runway["runways"] and runway["remaining_estimate_chapters"] >= 24
    for row in runway["runways"]:
        assert row["verdict"] in ("sufficient", "insufficient", "unknown")
        assert row["required_units"] >= 1
    assert any(row["verdict"] == "insufficient" for row in runway["runways"])
    assert runway["insufficient_runways"]
    thin = [item for item in runway["findings"]
            if item["code"] == "STRUCTURE_TOO_THIN_FOR_REMAINING_TARGET"]
    assert thin and runway["insufficient_runways"][0] in thin[0]["message"]
    assert spine["route_identity"]
    if spine["route_review_required"]:
        codes = {item["code"] for item in runway["findings"]}
        assert "AUTHOR_ROUTE_REVIEW_REQUIRED" in codes    # 只提示，不自动换 route
    _ = summary


def test_evidence_gap_and_state_conflict_domains(tmp_path: Path) -> None:
    service, _ = _run(tmp_path)
    target = _artifact(service, "LEGACY_TARGET_ALIGNMENT.json")
    targets = target["targets"]
    evidence_gaps = [row for row in targets
                     if row["gap_subtype"] == "semantic_evidence_gap"]
    assert evidence_gaps, "存在 semantic_evidence_gap"
    tags = {tag for row in evidence_gaps for tag in row["evidence_gap_subtypes"]}
    assert len(tags) >= 2 and all(row["evidence_gap_subtypes"] for row in evidence_gaps)
    state_conflicts = [row for row in targets
                       if row["conflict_subtype"] == "state_binding_conflict"]
    assert len(state_conflicts) == 16
    assert all(row["state_domain"] for row in state_conflicts)
    assert len({row["state_domain"] for row in state_conflicts}) >= 1
    for row in targets:
        assert row["primary_issue"] and row["recommended_repair_type"]
        assert row["required_validators"] and row["domain_tags"]
        assert row["human_review_required"] == (row["risk"] == "HUMAN_REQUIRED")
    types = {row["recommended_repair_type"] for row in targets}
    assert len(types) >= 3, "repair action 必须与细分类对应，不是全部 FIELD_REWRITE"


def test_repair_target_unique_ownership_and_batch_dag(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    target = _artifact(service, "LEGACY_TARGET_ALIGNMENT.json")
    plan = _artifact(service, "M11_BATCH_PLAN.json")
    readiness = _artifact(service, "M11_READINESS_REPORT.json")
    owners: dict[str, list[str]] = {}
    for batch in plan["batches"]:
        for chapter_id in batch["chapter_ids"]:
            owners.setdefault(chapter_id, []).append(batch["batch_id"])
        assert batch["mutable_target_count"] == len(batch["chapter_ids"])
        assert batch["risk_distribution"] and batch["validators"]
    assert sum(len(rows) > 1 for rows in owners.values()) == 0
    assert set(owners) == {row["chapter_id"] for row in target["targets"]}
    assert all(row["owning_repair_batch_id"] for row in target["targets"])
    assert summary["gate"].repair_ownership_coverage == 372
    assert summary["gate"].batch_dag_valid is True
    assert readiness["topological_order"] and len(readiness["topological_order"]) == 17
    statuses = {row["batch_id"]: row["status"] for row in readiness["batches"]}
    assert statuses["REPAIR_BATCH_01"] == "READY"
    assert set(statuses.values()) <= {"READY", "BLOCKED_AUTHOR_DECISION",
                                      "BLOCKED_DEPENDENCY", "BLOCKED_STRUCTURE"}
    assert any(row["status"] == "BLOCKED_DEPENDENCY" for row in readiness["batches"])
    assert readiness["ready_batch_ids"] == ["REPAIR_BATCH_01"]


def test_legacy_isolation_and_no_content_repair(tmp_path: Path) -> None:
    service, summary = _run(tmp_path)
    story_map = _artifact(service, "HISTORICAL_STORY_MAP.json")
    target = _artifact(service, "LEGACY_TARGET_ALIGNMENT.json")
    assert all(row["time_layer"] == "legacy_representation"
               for row in story_map["volumes"] + story_map["arcs"])
    for row in target["targets"]:
        assert set(row["forbidden_change_sources"]) <= set(CONFIRMED_SOURCES)
        if row["forbidden_changes"]:
            assert row["forbidden_change_sources"], row["chapter_id"]
    assert summary["gate"].legacy_isolation_ok is True
    # 没有 repair：队列与 happened digests 都不变
    before = summary["baseline"]
    after = service.baseline()
    assert before.happened_digests() == after.happened_digests()
    assert after.queue_counts == {CONFIRMED: 198, FIELD_CONFLICT: 27, CONTENT_GAP: 345}
    assert summary["gate"].status == "PASS" and summary["gate"].ok() is True
