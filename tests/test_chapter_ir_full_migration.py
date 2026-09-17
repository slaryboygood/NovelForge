"""FM01–FM05：Full Shadow Migration 输出与硬边界回归。

真实产物在 workspace（gitignored）→ 缺文件时 SKIP；同时提供不依赖实例的合成单测。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from novelforge.story_engine.chapter_ir.migration import LegacyChapterMigration
from novelforge.story_engine.chapter_ir.state import (
    TransitionBinding,
    build_default_registry,
)

FULL_DIR = Path("workspace/wasteland_001_exports/chapter_ir_v1/full_migration")
FULL_JSON = FULL_DIR / "WASTELAND_001_CHAPTER_IR_FULL.json"
QUEUE_JSON = FULL_DIR / "WASTELAND_001_CHAPTER_IR_CONTENT_REPAIR_QUEUE.json"
SAMPLE_MD = FULL_DIR / "WASTELAND_001_CHAPTER_IR_FULL_MIGRATION_SAMPLE.md"
GOLDEN_MD = FULL_DIR / "WASTELAND_001_CHAPTER_IR_GOLDEN_REGRESSION.md"
CANDIDATE = Path("workspace/wasteland_001_exports/WASTELAND_001_OUTLINE_CANON_FINAL_CANDIDATE_V5.json")


def _load() -> dict:
    if not FULL_JSON.is_file():
        pytest.skip("full migration 产物不存在（dogfood 数据不在 git 内）")
    return json.loads(FULL_JSON.read_text(encoding="utf-8"))


def test_full_migration_covers_all_chapters_with_stable_identity() -> None:
    data = _load()
    chapters = data["chapters"]
    assert len(chapters) == 570
    uuids = [row["chapter_uuid"] for row in chapters]
    assert len(set(uuids)) == 570
    assert all("ch" not in uuid for uuid in uuids)
    assert all(row["display_number"] for row in chapters)


def test_disposition_covers_every_chapter_and_matches_queue() -> None:
    data = _load()
    queue = json.loads(QUEUE_JSON.read_text(encoding="utf-8"))
    queue_ids = {item["chapter_uuid"] for item in queue["items"]}
    repair_dispositions = {"NEEDS_CONTENT_REPAIR", "MIGRATION_AMBIGUOUS", "PRODUCT_RULE_REVIEW"}
    for row in data["chapters"]:
        assert row["disposition"] in {"READY_TO_COMPILE", "READY_WITH_OPTIONAL_NA",
                                      "NEEDS_CONTENT_REPAIR", "MIGRATION_AMBIGUOUS",
                                      "PRODUCT_RULE_REVIEW"}
        if row["disposition"] in repair_dispositions:
            assert row["chapter_uuid"] in queue_ids
        else:
            assert row["chapter_uuid"] not in queue_ids


def test_golden_semantic_accuracy_is_full() -> None:
    data = _load()
    golden = data["report"]["golden"]
    assert golden["total"] >= 15
    assert golden["accuracy"] == 1.0
    assert all(row["matched"] for row in golden["rows"].values())
    assert GOLDEN_MD.is_file()


def test_shadow_migration_does_not_touch_inputs() -> None:
    data = _load()
    report = data["report"]
    assert report["candidate_digest_before"] == report["candidate_digest_after"]
    assert report["story_state_digest_before"] == report["story_state_digest_after"]
    if report["canon_digest_before"]:
        assert report["canon_digest_before"] == report["canon_digest_after"]
    digest = hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()[:16]
    assert digest == report["candidate_digest_after"]
    assert report["writer_machine_token_hits"] == 0
    assert SAMPLE_MD.is_file()


def test_state_replay_is_legal_in_narrative_order() -> None:
    data = _load()
    replay = data["report"]["state_replay"]
    assert isinstance(replay, list)
    orders = [row["display_number"] for row in replay]
    assert orders == sorted(orders)
    queue = json.loads(QUEUE_JSON.read_text(encoding="utf-8"))
    flagged_displays = {item["display_number"] for item in queue["items"]}
    for row in replay:
        if not row["legal"]:
            assert row["display_number"] in flagged_displays


def test_disposition_upgrade_rules_without_instance_data() -> None:
    """合成单测：conditional 字段只有 NA → READY_WITH_OPTIONAL_NA 语义；blocked required → repair。"""

    class _IR:
        ambiguous_entity_ids: list[str] = []

    assert LegacyChapterMigration.disposition(_IR(), set(), blocked_fields=[]) == "READY_TO_COMPILE"
    assert LegacyChapterMigration.disposition(_IR(), set(),
                                              blocked_fields=["decision"]) == \
        "NEEDS_CONTENT_REPAIR"
    assert LegacyChapterMigration.disposition(_IR(), {"PREMATURE_STATE_TRANSITION"}) == \
        "NEEDS_CONTENT_REPAIR"
    assert LegacyChapterMigration.disposition(_IR(), {"DOG_BINDING_PLUMBING_ERROR"}) == \
        "PRODUCT_RULE_REVIEW"


def test_cross_chapter_replay_rejects_early_acquisition() -> None:
    registry = build_default_registry({})
    registry.bind(TransitionBinding("salt_route_control",
                                    "controlled_by_rust_settlement", "uuid_133", 133))
    early = [{"id": "ch090", "display_number": 90, "state_key": "salt_route_control",
              "to_state": "controlled_by_rust_settlement", "mode": "transition"}]
    from novelforge.story_engine.chapter_ir.models import ChapterStateTransition
    findings = registry.validate([ChapterStateTransition(
        transition_id="ST_001", state_key="salt_route_control", from_state="contested",
        to_state="controlled_by_rust_settlement", transition_kind="acquisition",
        effective_at=90)], chapter_position=90)
    assert "PREMATURE_STATE_TRANSITION" in {item.code for item in findings}
