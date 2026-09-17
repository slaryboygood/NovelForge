"""S09：Semantic Reconciliation 回归（verifier 规则 + queue V2 + binding 优先）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelforge.story_engine.chapter_ir.builder import ChapterIRBuilder
from novelforge.story_engine.chapter_ir.compiler import ChapterFieldCompiler
from novelforge.story_engine.chapter_ir.extractor import (
    ExtractedChapterIRProposal,
    LegacyIRSemanticExtractor,
)
from novelforge.story_engine.chapter_ir.state import (
    TransitionBinding,
    build_default_registry,
)
from novelforge.story_engine.chapter_ir.verifier import (
    AUTHORITATIVE_BINDING_CONFLICT,
    DECISION_WRONG_ACTOR,
    DOG_PASSIVE_AS_SUPPORTIVE,
    DeterministicSemanticVerifier,
    categorize,
)

RECON_DIR = Path("workspace/wasteland_001_exports/chapter_ir_v1/reconciliation")
RECON_JSON = RECON_DIR / "WASTELAND_001_CHAPTER_IR_SEMANTIC_RECONCILIATION.json"
QUEUE_V2 = RECON_DIR / "WASTELAND_001_CHAPTER_IR_REPAIR_QUEUE_V2.json"

ALIASES = {"主角": "ENTITY_PROTAGONIST", "阿灰": "ENTITY_DOG_AHUI",
           "编号犬": "ENTITY_HUNTER_DOG_01"}
KIND_INDEX = {"dog": ["ENTITY_DOG_AHUI", "ENTITY_HUNTER_DOG_01"]}


def _extractor() -> LegacyIRSemanticExtractor:
    return LegacyIRSemanticExtractor(
        novel_id="n1", dog_entity_id="ENTITY_DOG_AHUI",
        protagonist_id="ENTITY_PROTAGONIST", entity_aliases=ALIASES, kind_index=KIND_INDEX)


def _ir(chapter: dict):
    extractor = _extractor()
    return extractor.to_ir(extractor.extract(chapter, backend="deterministic"), chapter)


def test_decision_owner_must_be_focal_owner() -> None:
    chapter = {"id": "chx", "chapter_uuid": "uuid_x", "display_number": 10,
               "goal": "在断水前决定去哪找活路",
               "events": ["营地边有人议论井见底", "代表宣布名单建立者是最初的塔"]}
    ir = _ir(chapter)
    assert not [event for event in ir.event_frames if event.decision_action]
    check = DeterministicSemanticVerifier().verify(ir, chapter)
    assert DECISION_WRONG_ACTOR not in check.issues


def test_dog_mention_is_not_actor_and_passive_is_not_supportive() -> None:
    chapter = {"id": "chy", "chapter_uuid": "uuid_y", "display_number": 11,
               "goal": "守住地窖门口",
               "events": ["阿灰的编号被登记在册", "阿灰被落石困在通道里"]}
    ir = _ir(chapter)
    for event in ir.event_frames:
        assert "ENTITY_DOG_AHUI" not in event.actor_ids
    check = DeterministicSemanticVerifier().verify(ir, chapter)
    assert DOG_PASSIVE_AS_SUPPORTIVE not in check.issues


def test_payoff_equal_to_hook_is_flagged() -> None:
    chapter = {"id": "chz", "chapter_uuid": "uuid_z", "display_number": 12,
               "goal": "处理存水争议", "trigger": "有人偷偷存水",
               "hook": "有人开始偷偷存水", "payoff": "有人开始偷偷存水",
               "events": ["韩彻当众清点水桶", "居民接受轮流取水"]}
    ir = _ir(chapter)
    check = DeterministicSemanticVerifier().verify(ir, chapter)
    assert "LEGACY_PAYOFF_FIELD_CONFLICT" in check.payoff.issues


def test_authoritative_binding_conflict_is_detected() -> None:
    chapter = {"id": "chw", "chapter_uuid": "uuid_w", "display_number": 200,
               "goal": "讨论共守规矩的表决安排",
               "events": ["各方围绕共守草案完成表决"]}
    ir = _ir(chapter)
    registry = build_default_registry({})
    registry.bind(TransitionBinding("common_rules_status", "voted", "uuid_526", 526))
    check = DeterministicSemanticVerifier().verify(ir, chapter, registry)
    assert AUTHORITATIVE_BINDING_CONFLICT in check.issues


def test_cost_loss_duplicate_only_renders_once() -> None:
    chapter = {"id": "chv", "chapter_uuid": "uuid_v", "display_number": 30,
               "goal": "押货穿过旧道", "cost": "半车货被夺", "loss": "半车货被夺",
               "events": ["韩彻押货走旧道", "伏击队抢走半车货", "他把人带回铁锈集"]}
    ir = _ir(chapter)
    compiled = ChapterFieldCompiler(actor_names={"ENTITY_PROTAGONIST": "韩彻"}).compile(ir)
    preview = compiled.writer_preview()
    assert ("cost" in preview) ^ ("loss" in preview)


def test_categorize_priority() -> None:
    assert categorize(verified="DISAGREE", deterministic_ok=False, conflicts=[], wrong_actor=True,
                      ambiguous=False) == "EXTRACTION_REPAIR"
    assert categorize(verified="AGREE", deterministic_ok=True, conflicts=[], wrong_actor=False,
                      ambiguous=False) == "SEMANTIC_CONFIRMED"
    assert categorize(verified="AGREE", deterministic_ok=False, conflicts=["world_state_change"],
                      wrong_actor=False, ambiguous=False) == "LEGACY_FIELD_CONFLICT"
    assert categorize(verified="AMBIGUOUS", deterministic_ok=False, conflicts=[], wrong_actor=False,
                      ambiguous=True) == "HUMAN_CANON_DECISION"


def test_reconciliation_outputs_when_present() -> None:
    if not RECON_JSON.is_file():
        pytest.skip("reconciliation 产物不存在（dogfood 数据不在 git 内）")
    data = json.loads(RECON_JSON.read_text(encoding="utf-8"))
    stats = data["statistics"]
    assert data["chapter_count"] == 570
    assert stats["decision_wrong_actor_count"] == 0
    assert stats["primary_transition_wrong_count"] == 0
    assert stats["writer_machine_token"] == 0
    assert stats["cost_loss_duplicate_writer_output"] == 0
    queue = json.loads(QUEUE_V2.read_text(encoding="utf-8"))
    confirmed = {row["chapter_uuid"] for row in data["chapters"]
                 if row["category"] == "SEMANTIC_CONFIRMED"}
    queued = {row["chapter_uuid"] for row in queue["items"]}
    assert not (confirmed & queued)
