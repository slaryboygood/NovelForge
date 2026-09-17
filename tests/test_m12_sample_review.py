"""M12 人工样本回归：分层抽样 / delegated conservative verdict / freeze 前人工面。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.m12_acceptance import (
    DELEGATION,
    M12FullBookAuditService,
    M12PreflightService,
    M12SampleReviewService,
    SAMPLE_REVIEW_DOC,
    SAMPLE_REVIEW_FILE,
    SAMPLE_SEED,
    SAMPLE_SIZE,
)

from m12_phase_history import load_phase_snapshot, verify_phase_snapshot

ROOT = Path(".").resolve()
DESIGN_DIR = ROOT / "workspace/wasteland_001_exports/repair_adoption_v1"
M12_DIR = DESIGN_DIR / "m12"


@pytest.fixture(scope="module")
def sample_review():
    M12PreflightService(ROOT).run()
    M12FullBookAuditService(ROOT).run()
    service = M12SampleReviewService(ROOT)
    payload = service.run()
    return service, payload


def _artifact(name: str) -> dict:
    return json.loads((M12_DIR / name).read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- selection
def test_sample_selection_is_deterministic(sample_review) -> None:
    service, payload = sample_review
    first = service.selection()
    second = service.selection()
    assert first["rows"] == second["rows"]
    assert first["seed"] == SAMPLE_SEED
    assert len(first["rows"]) == SAMPLE_SIZE
    assert [row["legacy_label"] for row in first["rows"]] == [
        row["legacy_label"] for row in payload["selection"]["rows"]]


def test_sample_strata_cover_all_dimensions(sample_review) -> None:
    _service, payload = sample_review
    coverage = payload["selection"]["coverage"]
    assert coverage["all_volumes_covered"] is True
    assert coverage["all_subtypes_covered"] is True
    assert coverage["all_modes_covered"] is True
    assert len(coverage["volumes_covered"]) == 10
    assert coverage["author_review_items"], "author lane 必须出现在人工样本中"
    strata = payload["selection"]["strata"]
    for key in ("volume", "subtype", "mode", "author_review",
                "materialization", "unresolved_heavy"):
        assert strata[key], key


# ---------------------------------------------------------------- verdicts
def test_all_sample_items_review_clean(sample_review) -> None:
    _service, payload = sample_review
    assert payload["status"] == "PASS"
    assert all(payload["checks"].values()), payload["checks"]
    assert payload["failures"] == []
    assert payload["sample_size"] == SAMPLE_SIZE
    for row in payload["reviews"]:
        assert row["verdict"] == "ACCEPT", row["legacy_label"]
        assert all(row["checks"].values()), (row["legacy_label"], row["checks"])
        assert row["checks"]["truth_boundary_ok"] is True
        assert row["checks"]["no_canon_mutation"] is True
        assert row["checks"]["writer_projection_ready"] is True


def test_delegated_decisions_have_audit_trail(sample_review) -> None:
    _service, payload = sample_review
    delegated = payload["delegated_decisions"]
    assert payload["checks"]["delegation_audited"] is True
    for row in delegated:
        assert row["delegation"] == DELEGATION
        assert row["audit_trail"]
        assert row["evidence"]
        assert row["verdict"] == "ACCEPT"
    override = payload["author_override_recommended"]
    assert len(override) == len(delegated)
    for row in override:
        assert row["legacy_label"] and row["topic"]


def test_sample_covers_repair_targets_and_non_targets(sample_review) -> None:
    _service, payload = sample_review
    targets = [row for row in payload["reviews"] if row["repair_target"]]
    non_targets = [row for row in payload["reviews"] if not row["repair_target"]]
    assert targets, "样本必须包含 repair target 章节"
    for row in targets:
        assert row["repair_subtype"]
    for row in non_targets:
        assert row["repair_subtype"] == ""
        assert row["checks"]["repair_lineage_ok"] is True


# ---------------------------------------------------------------- doc + snapshot
def test_sample_review_doc_generated(sample_review) -> None:
    _service, payload = sample_review
    doc = (ROOT / SAMPLE_REVIEW_DOC).read_text(encoding="utf-8")
    assert "M12 人工样本审核包" in doc
    assert f"样本规模：**{payload['sample_size']}**" in doc
    for row in payload["reviews"]:
        assert f"### {row['legacy_label']}" in doc
    assert "作者 override 建议" in doc


def test_sample_review_snapshot_frozen(sample_review) -> None:
    _service, payload = sample_review
    assert verify_phase_snapshot("M12_SAMPLE_REVIEW")["status"] == "PASS"
    snapshot = load_phase_snapshot("M12_SAMPLE_REVIEW")
    assert snapshot["status"] == "PASS"
    assert snapshot["sample_size"] == SAMPLE_SIZE
    assert snapshot["seed"] == SAMPLE_SEED
    assert snapshot["failure_count"] == 0
    assert snapshot["sample_labels"] == [row["legacy_label"]
                                         for row in payload["reviews"]]
    assert snapshot["review_doc"] == SAMPLE_REVIEW_DOC


def test_sample_review_does_not_mutate_frozen_inputs(sample_review) -> None:
    _service, _payload = sample_review
    guard = _artifact("M11_FROZEN_INPUT.json")
    for name, digest in guard["m11_frozen_artifacts"].items():
        assert _digest(DESIGN_DIR / name) == digest, name
    assert _artifact(SAMPLE_REVIEW_FILE)["status"] == "PASS"
