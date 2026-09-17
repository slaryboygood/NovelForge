"""P15m：Micro Semantic Repair Wave 01 + hardened pivot consequence gate 回归。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m11_micro_pilot import MicroPilotService
from novelforge.story_engine.m11_micro_wave import (
    CONSEQUENCE_STRENGTH,
    MicroWaveExecutor,
    wave_pivot_evidence,
)

ROOT = Path(".").resolve()


@pytest.fixture(scope="module")
def wave():
    service = MicroWaveExecutor(ROOT)
    payload = service.run()
    return service, payload


def _artifact(service: MicroWaveExecutor, name: str):
    return json.loads((service.wave_dir / name).read_text(encoding="utf-8"))


def test_pilot_hardened_gate_pass() -> None:
    service = MicroPilotService(ROOT)
    service.run()
    hardening = json.loads((service.pilot_dir / "MICRO_GATE_HARDENING.json")
                           .read_text(encoding="utf-8"))
    assert hardening["pilot_pass"] == 3 and hardening["pilot_fail"] == 0
    assert "PIVOT_CONSEQUENCE_REQUIRED" in hardening["gate_checks"]
    reconciliation = json.loads((service.pilot_dir / "MICRO_PILOT_RECONCILIATION.json")
                                .read_text(encoding="utf-8"))
    assert reconciliation["status"] == "PILOT_UNCHANGED"
    assert reconciliation["repair_records_modified"] is False


def test_observation_alone_cannot_be_turn(wave) -> None:
    service, _payload = wave
    inputs = service.pilot.load()
    artifact = next(row for row in inputs.artifacts.values()
                    if row.chapter_ir.event_frames)
    for row in wave_pivot_evidence(artifact):
        assert row["consequences"]
        assert CONSEQUENCE_STRENGTH[row["strongest"]] >= 1
    candidates = _artifact(service, "MICRO_WAVE_CANDIDATES.json")
    for row in candidates["candidates"]:
        consequence = row["patch"]["pivot_consequence"]
        assert consequence["source_event_ids"]
        assert consequence["derived_semantic"] is True
        assert consequence["before"] != consequence["after"]
        assert row["semantics_added"]["event_added"] == 0


def test_frontier_planner_limits_and_dedup(wave) -> None:
    service, _payload = wave
    scope = _artifact(service, "MICRO_REPAIR_WAVE_01_SCOPE.json")
    assert scope["selected_count"] <= 12
    assert scope["selected_count"] == scope["eligible_count"]
    labels = [row["legacy_label"] for row in scope["selected"]]
    assert len(labels) == len(set(labels))
    assert all(row["eligible"] for row in scope["selected"])
    assert all(row["ineligible_reason"] for row in scope["ineligible"])
    assert scope["no_literary_score"] is True
    assert all(row["reuse_events"] for row in scope["selected"])
    _ = service


def test_wave_adjudication_and_queue_lineage(wave) -> None:
    service, payload = wave
    adjudication = _artifact(service, "MICRO_WAVE_ADJUDICATION.json")
    assert adjudication["no_default_preference"] is True
    assert adjudication["status_counts"].get("CONTENT_REWRITE_REQUIRED", 0) >= 1
    approvals = _artifact(service, "MICRO_WAVE_APPROVALS.json")
    assert approvals["not_author_decision"] is True
    assert all(row["approval_kind"] == "MANUAL_OPERATOR"
               and row["pivot_consequence_digest"]
               for row in approvals["approvals"])
    queue = _artifact(service, "MICRO_WAVE_QUEUE_RESOLUTION.json")
    assert queue["resolved_count"] == payload["promoted"]
    assert queue["items_deleted"] == 0
    for row in queue["items"]:
        if row.get("status") == "RESOLVED":
            assert row["status_history"][-1] == "RESOLVED_REPAIRED"


def test_promotion_release_and_overlay(wave) -> None:
    service, payload = wave
    promotion = _artifact(service, "MICRO_WAVE_PROMOTION.json")
    assert promotion["promoted_count"] == payload["promoted"] >= 1
    for row in promotion["promoted"]:
        added = row["semantics_added"]
        assert added["event_added"] == 0 and added["turn_added"] == 1
        assert added["transition_added"] == 0
        assert added["field_evidence_added"] == 1
    release = _artifact(service, "MICRO_WAVE_BLOCKER_RELEASE.json")
    assert release["deduped"] is True
    assert payload["batch_repair_executed"] is False
    overlay = json.loads((service.design_dir / "M11_OVERLAY_V2.json")
                         .read_text(encoding="utf-8"))
    assert overlay["conservation"]["exact"] is True
    assert overlay["repaired_micro_semantic"] >= 3
    assert overlay["baseline_queue_counts"] == {"SEMANTIC_CONFIRMED": 198,
                                               "LEGACY_FIELD_CONFLICT": 27,
                                               "LEGACY_CONTENT_GAP": 345}


def test_scale_assessment_and_truth_boundary(wave) -> None:
    service, payload = wave
    assessment = _artifact(service, "MICRO_REPAIR_SCALE_ASSESSMENT.json")
    assert assessment["verdict"] in ("READY_TO_SCALE",
                                     "HOLD_FOR_REPAIR_POLICY_FIX")
    assert assessment["statistics"]["new_facts"] == 0
    assert assessment["statistics"]["confirmed_facts_changed"] == 0
    assert assessment["statistics"]["pivot_consequence_failure"] == 0
    gate = _artifact(service, "P15M_GATE.json")
    assert gate["status"] == "PASS"
    assert all(gate["checks"].values()), [k for k, v in gate["checks"].items() if not v]
    assert payload["author_items_untouched"] and payload["entity_items_untouched"]
    for path in (ROOT / "novel/authoring/story_engine/canon/wasteland_001.sqlite",
                 ROOT / "novel/authoring/story_engine/state/runtime_wasteland_001/"
                        "v000001.json",
                 ROOT / "workspace/wasteland_001_exports/"
                        "WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json",
                 ROOT / "workspace/wasteland_001_exports/chapter_ir_v1/"
                        "full_migration/WASTELAND_001_CHAPTER_IR_FULL.json"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        assert digest in ("73836dada9d6bf8e", "bbc67137eefb9c55", "cc144c76796d6a4c",
                          "2eaac16d66e39421")
