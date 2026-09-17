"""S04/S05：legacy migration 的真实 regression fixture（generic，不写实例人名）。

抽象自 V5 的典型坏例：ch092 型（cost 写成事件）、ch202 型（字段复制 event）、
ch361 型（cost 不是 cost）、ch419 型（decision 写成结果）、ch515 型（草案章混入签署状态）、
ch559 型（正式签署却仍带旧 frame），以及 display renumber 稳定性。
"""

from __future__ import annotations

from novelforge.story_engine.chapter_ir.builder import ChapterIRBuilder
from novelforge.story_engine.chapter_ir.compiler import ChapterFieldCompiler
from novelforge.story_engine.chapter_ir.evidence import EvidenceValidator
from novelforge.story_engine.chapter_ir.state import build_default_registry
from novelforge.story_engine.chapter_ir.validator import ChapterIRValidator

NAME_TO_ID = {"主角": "hero", "阿灰": "dog", "同伴": "ally"}


def _chapter(**overrides) -> dict:
    base = {
        "id": "ch092", "chapter_uuid": "uuid_092", "display_number": 92, "volume": 2, "arc": "A6",
        "goal": "把私存物摆到台面上公开分配",
        "events": ["主角把私存物摆到棚口逐件登记", "主角决定公开全部分配口径",
                   "主角当众把账目念完"],
        "decision": "按本章做法处理：主角把私存物摆到棚口逐件登记",
        "cost": "付出：主角把私存物摆到棚口逐件登记",
        "loss": "无", "payoff": "账目公开，居民接受分配",
        "world_state_change": "分配程序被公开检验", "dog_role": "absent",
        "dog_note": "", "information_release": "私存物数目被公开",
    }
    base.update(overrides)
    return base


def _build(chapter: dict):
    builder = ChapterIRBuilder(novel_id="n1", dog_id="dog", dog_name="阿灰",
                               protagonist_id="hero", actor_names=NAME_TO_ID)
    return builder.from_legacy(chapter, name_to_id=NAME_TO_ID,
                               index=chapter.get("display_number") or 0)


def test_ch092_type_cost_copy_is_detected() -> None:
    ir = _build(_chapter())
    report = EvidenceValidator(protagonist_id="hero", dog_id="dog").validate(
        ir, candidate_fields={"cost": ir.event_frames[0].action_text})
    assert "COST_WITHOUT_NEGATIVE_EFFECT" in report.codes() or \
        "FIELD_EVENT_COPY_WITHOUT_ROLE" in report.codes()


def test_ch419_type_decision_result_is_detected() -> None:
    chapter = _chapter(id="ch419", display_number=419,
                       goal="在提前高峰中把队伍带出困境",
                       events=["高峰提前，队伍被困在坡下", "主角改走侧沟脱身"],
                       decision="高峰提前、队伍被困、主角改走侧沟")
    report = EvidenceValidator(protagonist_id="hero").validate(
        _build(chapter), candidate_fields={"decision": "高峰提前、队伍被困、主角改走侧沟"})
    assert "DECISION_WITHOUT_DECISION_EVENT" in report.codes()


def test_ch515_type_draft_chapter_must_not_be_signed() -> None:
    chapter = _chapter(id="ch515", display_number=515,
                       goal="把共守草案带到盆地边缘征求意见",
                       events=["主角带草案到边缘聚落", "聚落代表逐条追问",
                               "有争议的三条被圈出来带回修订"],
                       world_state_change="共守规矩成立，新秩序成立")
    ir = _build(chapter)
    ir.temporal_position = 515
    registry = build_default_registry({"common_rules_status": 526})
    report = ChapterIRValidator(registry=registry).validate(ir)
    assert {"PREMATURE_STATE_TRANSITION", "ILLEGAL_STATE_EDGE"} & set(report.codes())


def test_ch559_type_signature_chapter_is_legal() -> None:
    chapter = _chapter(id="ch559", display_number=559,
                       goal="用并列署名完成正式签署",
                       events=["各方代表聚在塔壁前", "主角拒绝编号所有权条款",
                               "主角刻下并列两个名字", "各方依次落笔，共守规矩正式生效"],
                       world_state_change="共守规矩正式签署生效")
    ir = _build(chapter)
    ir.temporal_position = 559
    registry = build_default_registry({"common_rules_status": 526})
    report = ChapterIRValidator(registry=registry).validate(ir)
    assert "PREMATURE_STATE_TRANSITION" not in report.codes()


def test_renumber_does_not_change_ir_identity_or_evidence() -> None:
    before = _build(_chapter(display_number=92))
    after = _build(_chapter(display_number=78))
    assert before.chapter_uuid == after.chapter_uuid
    assert [item.event_id for item in before.event_frames] == \
        [item.event_id for item in after.event_frames]
    assert [item.event_ids for item in before.field_evidence] == \
        [item.event_ids for item in after.field_evidence]


def test_compiled_fields_pass_evidence_gate() -> None:
    ir = _build(_chapter())
    registry = build_default_registry({})
    compiled = ChapterFieldCompiler(actor_names=NAME_TO_ID).compile(ir)
    fields = {item.field_name: item.text for item in compiled.fields}
    report = ChapterIRValidator(registry=registry).validate(ir, candidate_fields=fields)
    assert "WRITER_VISIBLE_METADATA_LEAK" not in report.codes()
    assert "DECISION_WITHOUT_DECISION_EVENT" not in report.codes()
